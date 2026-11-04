import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.interview import router as interview_router
from app.database.base import Base
from app.database.session import get_db
from app.models.candidate import Candidate
from app.models.interview import Answer, InterviewSession, Question
from app.schemas.answer import MAX_ANSWER_LENGTH

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
    test_app.include_router(interview_router, prefix="/api")
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
    return _build_session(db_session)


def _answer_url(session_id: str, question_id: str) -> str:
    return f"/api/interviews/{session_id}/questions/{question_id}/answers"


# --- Submission ------------------------------------------------------------


def test_submit_answer_persists_and_returns_record(client, interview, db_session):
    question = interview.questions[0]

    response = client.post(
        _answer_url(interview.id, question.id),
        json={"answer_text": "I would shard the write path and add an idempotency key."},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["question_id"] == question.id
    assert payload["session_id"] == interview.id
    assert payload["question_position"] == 1
    assert payload["answer_text"] == "I would shard the write path and add an idempotency key."
    assert payload["created_at"]
    assert payload["updated_at"]

    stored = db_session.query(Answer).one()
    assert stored.id == payload["id"]
    assert stored.session_id == interview.id
    assert stored.question_id == question.id
    assert stored.answer_text == "I would shard the write path and add an idempotency key."


def test_submit_answer_strips_surrounding_whitespace_but_keeps_line_breaks(client, interview):
    question = interview.questions[1]

    response = client.post(
        _answer_url(interview.id, question.id),
        json={"answer_text": "  First point.\n\nSecond point.  \n"},
    )

    assert response.status_code == 201
    assert response.json()["answer_text"] == "First point.\n\nSecond point."


def test_answer_appears_in_session_answer_list(client, interview):
    question = interview.questions[0]
    created = client.post(
        _answer_url(interview.id, question.id),
        json={"answer_text": "Caching with a short TTL."},
    ).json()

    response = client.get(f"/api/interviews/{interview.id}/answers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == interview.id
    assert payload["total_questions"] == 3
    assert payload["answered_count"] == 1
    assert payload["answers"] == [created]


def test_answers_are_listed_in_question_order(client, interview):
    for index in (2, 0):
        question = interview.questions[index]
        response = client.post(
            _answer_url(interview.id, question.id),
            json={"answer_text": f"Answer for question {question.position}."},
        )
        assert response.status_code == 201

    payload = client.get(f"/api/interviews/{interview.id}/answers").json()

    assert [answer["question_position"] for answer in payload["answers"]] == [1, 3]
    assert payload["answered_count"] == 2
    assert payload["total_questions"] == 3


def test_new_session_has_no_answers(client, interview):
    payload = client.get(f"/api/interviews/{interview.id}/answers").json()

    assert payload["answers"] == []
    assert payload["answered_count"] == 0
    assert payload["total_questions"] == 3


# --- Duplicate prevention --------------------------------------------------


def test_duplicate_answer_is_rejected(client, interview, db_session):
    question = interview.questions[0]
    first = client.post(
        _answer_url(interview.id, question.id),
        json={"answer_text": "Original answer."},
    )
    assert first.status_code == 201

    second = client.post(
        _answer_url(interview.id, question.id),
        json={"answer_text": "A replacement answer."},
    )

    assert second.status_code == 409
    assert "already been answered" in second.json()["detail"]
    assert db_session.query(Answer).count() == 1
    assert db_session.query(Answer).one().answer_text == "Original answer."


def test_duplicate_answer_is_prevented_by_the_database_constraint(db_session, interview):
    question = interview.questions[0]
    db_session.add(Answer(session=interview, question=question, answer_text="First."))
    db_session.commit()

    db_session.add(Answer(session=interview, question=question, answer_text="Second."))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert db_session.query(Answer).count() == 1


# --- Validation ------------------------------------------------------------


@pytest.mark.parametrize("answer_text", ["", "   ", "\n\t  \n"])
def test_empty_answers_are_rejected(client, interview, db_session, answer_text):
    response = client.post(
        _answer_url(interview.id, interview.questions[0].id),
        json={"answer_text": answer_text},
    )

    assert response.status_code == 422
    assert db_session.query(Answer).count() == 0


def test_missing_answer_field_is_rejected(client, interview):
    response = client.post(_answer_url(interview.id, interview.questions[0].id), json={})

    assert response.status_code == 422


def test_overlong_answer_is_rejected(client, interview, db_session):
    response = client.post(
        _answer_url(interview.id, interview.questions[0].id),
        json={"answer_text": "x" * (MAX_ANSWER_LENGTH + 1)},
    )

    assert response.status_code == 422
    assert db_session.query(Answer).count() == 0


def test_unknown_session_returns_404(client, interview):
    response = client.post(
        _answer_url("does-not-exist", interview.questions[0].id),
        json={"answer_text": "An answer."},
    )

    assert response.status_code == 404
    assert "does-not-exist" in response.json()["detail"]


def test_unknown_question_returns_404(client, interview, db_session):
    response = client.post(
        _answer_url(interview.id, "missing-question"),
        json={"answer_text": "An answer."},
    )

    assert response.status_code == 404
    assert "missing-question" in response.json()["detail"]
    assert db_session.query(Answer).count() == 0


def test_question_from_another_session_is_rejected(client, interview, db_session):
    other = _build_session(db_session, role="data-scientist")
    foreign_question = other.questions[0]

    response = client.post(
        _answer_url(interview.id, foreign_question.id),
        json={"answer_text": "An answer for the wrong session."},
    )

    assert response.status_code == 404
    assert foreign_question.id in response.json()["detail"]
    assert db_session.query(Answer).count() == 0


def test_answers_for_unknown_session_return_404(client):
    response = client.get("/api/interviews/unknown-session/answers")

    assert response.status_code == 404
    assert "unknown-session" in response.json()["detail"]


def test_answering_one_question_does_not_answer_others(client, interview, db_session):
    client.post(
        _answer_url(interview.id, interview.questions[0].id),
        json={"answer_text": "Only the first question."},
    )

    assert db_session.query(Answer).count() == 1
    remaining = db_session.query(Question).filter(Question.session_id == interview.id).count()
    assert remaining == 3


# --- Persistence -----------------------------------------------------------


def test_answers_survive_a_new_database_session(client, interview):
    question = interview.questions[0]
    client.post(
        _answer_url(interview.id, question.id),
        json={"answer_text": "Persisted across sessions."},
    )

    fresh = TestingSessionLocal()
    try:
        answers = fresh.query(Answer).filter(Answer.session_id == interview.id).all()
        assert len(answers) == 1
        assert answers[0].answer_text == "Persisted across sessions."
        assert answers[0].question.position == 1
    finally:
        fresh.close()


def test_deleting_a_session_deletes_its_answers(client, interview, db_session):
    client.post(
        _answer_url(interview.id, interview.questions[0].id),
        json={"answer_text": "This answer goes away with the session."},
    )
    assert db_session.query(Answer).count() == 1

    db_session.delete(interview)
    db_session.commit()

    assert db_session.query(Answer).count() == 0
    assert db_session.query(Question).count() == 0
