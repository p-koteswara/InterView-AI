import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.evaluations import router as evaluations_router
from app.database.base import Base
from app.database.session import get_db
from app.models.candidate import Candidate
from app.models.interview import Answer, AnswerEvaluation, InterviewReport, InterviewSession, Question
from app.schemas.evaluation import AnswerEvaluationResult
from app.services import evaluation as evaluation_service
from app.services.evaluation import AnswerEvaluation as AnswerEvaluationModel
from app.services.gemini_client import AIResponseError

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# --- Fixtures --------------------------------------------------------------


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    test_app = FastAPI()
    test_app.include_router(evaluations_router, prefix="/api")
    test_app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(test_app)


def _build_session(db_session, role: str = "backend-engineer", questions: int = 3) -> InterviewSession:
    candidate = Candidate(
        filename=f"{role}.txt",
        extracted_text="Candidate resume text.",
        profile_data={"name": "Priya Nair"},
    )
    session = InterviewSession(
        candidate=candidate,
        role=role,
        role_title=role.replace("-", " ").title(),
        focus_skills=["Python"],
    )
    session.questions = [
        Question(
            position=position,
            text=f"Question {position}: how would you design this?",
            question_type="technical" if position % 2 else "conceptual",
            difficulty="medium",
            topic=f"Topic {position}",
        )
        for position in range(1, questions + 1)
    ]
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.fixture
def interview(db_session):
    return _build_session(db_session, questions=3)


def _submit_answer(db_session, session: InterviewSession, position: int, text: str) -> Answer:
    question = next(q for q in session.questions if q.position == position)
    answer = Answer(session=session, question=question, answer_text=text)
    db_session.add(answer)
    db_session.commit()
    db_session.refresh(answer)
    return answer


# --- Helpers ---------------------------------------------------------------


def _fake_evaluation(
    technical: float,
    relevance: float,
    depth: float,
    clarity: float,
    topic: str,
) -> AnswerEvaluationModel:
    return AnswerEvaluationModel(
        technical_score=technical,
        relevance_score=relevance,
        depth_score=depth,
        clarity_score=clarity,
        overall_score=round((technical + relevance + depth + clarity) / 4, 2),
        feedback=f"Feedback for {topic}.",
        improvements=[f"Improve {topic} depth."],
        topic=topic,
    )


@pytest.fixture
def fake_evaluate_answer(monkeypatch):
    """Replace the AI answer evaluation with deterministic fakes."""

    def fake_evaluate(profile, role, question, answer: str):
        if answer.strip() == "Strong answer.":
            return _fake_evaluation(8.0, 8.0, 8.0, 8.0, question.topic)
        return _fake_evaluation(4.0, 5.0, 3.0, 4.0, question.topic)

    monkeypatch.setattr("app.api.evaluations.evaluate_answer", fake_evaluate)
    return fake_evaluate


@pytest.fixture
def no_report_narrative(monkeypatch):
    """Keep final report narrative generation offline by forcing the fallback path."""

    def raise_failure(*args, **kwargs):
        raise AIResponseError("Gemini unavailable in tests.")

    monkeypatch.setattr(evaluation_service, "generate_json_with_fallback", raise_failure)
    monkeypatch.setattr(
        evaluation_service.get_settings().__class__,
        "effective_gemini_api_key",
        "",
        raising=False,
    )
    return raise_failure


# --- Answer evaluation endpoints -------------------------------------------


def test_evaluate_all_submitted_answers_persists_evaluations(client, interview, db_session, fake_evaluate_answer):
    _submit_answer(db_session, interview, position=1, text="Strong answer.")
    _submit_answer(db_session, interview, position=3, text="A weaker answer.")

    response = client.post(f"/api/interviews/{interview.id}/evaluations")

    assert response.status_code == 201
    payload = response.json()
    assert payload["session_id"] == interview.id
    assert payload["total_questions"] == 3
    assert payload["answered_count"] == 2
    assert payload["evaluated_count"] == 2
    assert [evaluation["question_position"] for evaluation in payload["evaluations"]] == [1, 3]

    persisted = db_session.query(AnswerEvaluation).all()
    assert len(persisted) == 2
    assert db_session.query(AnswerEvaluation).count() == 2


def test_evaluate_answers_are_ordered_by_question_position(client, interview, db_session, fake_evaluate_answer):
    _submit_answer(db_session, interview, position=2, text="Answer two.")
    _submit_answer(db_session, interview, position=1, text="Answer one.")

    payload = client.post(f"/api/interviews/{interview.id}/evaluations").json()

    assert [evaluation["question_position"] for evaluation in payload["evaluations"]] == [1, 2]


def test_evaluations_are_refreshed_not_duplicated(client, interview, db_session, fake_evaluate_answer):
    _submit_answer(db_session, interview, position=1, text="Strong answer.")

    first = client.post(f"/api/interviews/{interview.id}/evaluations")
    second = client.post(f"/api/interviews/{interview.id}/evaluations")

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["evaluated_count"] == 1
    assert db_session.query(AnswerEvaluation).count() == 1


def test_get_evaluations_returns_persisted_results(client, interview, db_session, fake_evaluate_answer):
    _submit_answer(db_session, interview, position=1, text="Strong answer.")
    client.post(f"/api/interviews/{interview.id}/evaluations")

    response = client.get(f"/api/interviews/{interview.id}/evaluations")

    assert response.status_code == 200
    payload = response.json()
    assert payload["evaluated_count"] == 1
    assert payload["evaluations"][0]["technical_score"] == 8.0
    assert payload["evaluations"][0]["overall_score"] == 8.0


def test_evaluations_for_unknown_session_return_404(client):
    response = client.get("/api/interviews/unknown-session/evaluations")

    assert response.status_code == 404
    assert "unknown-session" in response.json()["detail"]


# --- Final report ----------------------------------------------------------


def test_generate_report_aggregates_evaluations(client, interview, db_session, fake_evaluate_answer, no_report_narrative):
    _submit_answer(db_session, interview, position=1, text="Strong answer.")
    _submit_answer(db_session, interview, position=3, text="A weaker answer.")

    evaluation_response = client.post(f"/api/interviews/{interview.id}/evaluations").json()
    assert evaluation_response["evaluated_count"] == 2

    response = client.post(f"/api/interviews/{interview.id}/report")

    assert response.status_code == 201
    report = response.json()
    assert report["session_id"] == interview.id
    assert report["candidate_id"]
    assert report["candidate_name"] == "Priya Nair"
    assert report["role"] == "backend-engineer"
    assert report["role_title"] == "Backend Engineer"
    assert report["question_count"] == 3
    assert report["answered_count"] == 2
    # Mean of the two answer overall scores (8.0 and 4.0).
    assert report["overall_score"] == 6.0
    assert report["strengths"] == ["Topic 1"]
    assert report["weaknesses"] == ["Topic 3"]
    assert report["recommended_topics"] == ["Topic 3"]
    assert report["assessment"]

    persisted_report = db_session.query(InterviewReport).one()
    assert persisted_report.session_id == interview.id

    stored_evaluations = db_session.query(AnswerEvaluation).all()
    assert len(stored_evaluations) == 2


def test_generate_report_without_evaluations_returns_conflict(client, interview):
    response = client.post(f"/api/interviews/{interview.id}/report")

    assert response.status_code == 409
    assert "without answer evaluations" in response.json()["detail"]


def test_report_is_persisted_and_reused(client, interview, db_session, fake_evaluate_answer, no_report_narrative):
    _submit_answer(db_session, interview, position=1, text="Strong answer.")
    client.post(f"/api/interviews/{interview.id}/evaluations")
    first = client.post(f"/api/interviews/{interview.id}/report")
    assert first.status_code == 201

    second = client.post(f"/api/interviews/{interview.id}/report")

    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert db_session.query(InterviewReport).count() == 1


def test_get_report_returns_stored_report(client, interview, db_session, fake_evaluate_answer, no_report_narrative):
    _submit_answer(db_session, interview, position=1, text="Strong answer.")
    evaluation_response = client.post(f"/api/interviews/{interview.id}/evaluations")
    assert evaluation_response.status_code == 201
    created = client.post(f"/api/interviews/{interview.id}/report").json()

    response = client.get(f"/api/interviews/{interview.id}/report")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["overall_score"] == created["overall_score"]


def test_get_report_for_unknown_session_returns_404(client):
    response = client.get("/api/interviews/unknown-session/report")

    assert response.status_code == 404
    assert "unknown-session" in response.json()["detail"]
