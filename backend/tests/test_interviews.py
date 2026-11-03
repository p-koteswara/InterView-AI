import hashlib
import json
import re
import uuid
from pathlib import Path

import chromadb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.genai.errors import ServerError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.interview import router as interview_router
from app.core.config import get_settings
from app.core.job_roles import get_role
from app.database.base import Base
from app.database.session import get_db
from app.models.candidate import Candidate
from app.models.interview import InterviewSession, Question
from app.schemas.resume import (
    CandidateProfile,
    ExperienceItem,
    ProjectItem,
)
from app.services import question_generator
from app.services.gemini_client import AIResponseError
from app.services.question_generator import QuestionGenerationError
from app.services.rag import embeddings, ingestion, store

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

CORPUS = {
    "ai-ml-engineer/synthetic/optimization.txt": (
        "OPTIMIZATION AND GRADIENT DESCENT\n\n"
        "Gradient descent minimizes the loss by following the negative gradient. "
        "The learning rate controls the step size, and momentum smooths noisy updates. "
        "A learning rate that is too large diverges while one that is too small converges slowly.\n\n"
        "REGULARIZATION\n\n"
        "L2 weight decay penalizes large weights and reduces variance at the cost of bias.\n"
    ),
    "backend-engineer/synthetic/apis.txt": (
        "HTTP SEMANTICS AND IDEMPOTENCY\n\n"
        "Retrying a request safely requires an idempotency key so duplicate writes cannot occur. "
        "GET is safe and idempotent, POST is neither by default.\n"
    ),
    "data-scientist/synthetic/experiments.txt": (
        "HYPOTHESIS TESTING AND P VALUES\n\n"
        "A p value measures how surprising the observed data would be under the null hypothesis. "
        "Power analysis determines the sample size needed to detect an effect.\n"
    ),
}


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
def candidate(db_session):
    profile = CandidateProfile(
        name="Priya Nair",
        email="priya@example.com",
        programming_languages=["Python", "SQL"],
        frameworks_and_tools=["PyTorch", "FastAPI", "Docker"],
        technical_skills=["Model Evaluation", "Distributed Systems"],
        relevant_domains=["Machine Learning"],
        work_experience=[
            ExperienceItem(
                company="Acme Analytics",
                role="ML Engineer",
                duration="2022 - Present",
                description=["Trained ranking models", "Owned feature pipelines"],
            )
        ],
        projects=[
            ProjectItem(
                title="Churn prediction service",
                description="Gradient boosting model served behind a FastAPI endpoint",
                technologies=["Python", "XGBoost"],
            )
        ],
    )
    record = Candidate(
        filename="priya_nair.txt",
        extracted_text="Priya Nair - ML Engineer with Python, PyTorch and SQL experience.",
        profile_data=profile.model_dump(),
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def _hash_vector(text: str) -> list[float]:
    """Deterministic bag-of-words embedding for hermetic tests."""
    vector = [0.0] * get_settings().embedding_dimensions
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if len(token) < 3:
            continue
        index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % len(vector)
        vector[index] += 1.0
    return vector


def _fake_embed_texts(texts, task_type=embeddings.RETRIEVAL_DOCUMENT):
    return [_hash_vector(text) for text in texts]


@pytest.fixture
def vector_store(monkeypatch):
    """In-memory ChromaDB with a fake embedder, so tests never call the network."""
    monkeypatch.setattr(store, "_client", chromadb.EphemeralClient())
    monkeypatch.setattr(get_settings(), "chroma_collection", f"test_{uuid.uuid4().hex[:12]}")
    monkeypatch.setattr(embeddings, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")


@pytest.fixture
def indexed_corpus(vector_store, tmp_path: Path) -> Path:
    for relative, content in CORPUS.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    ingestion.ingest_corpus(tmp_path)
    return tmp_path


@pytest.fixture
def client(db_session):
    test_app = FastAPI()
    test_app.include_router(interview_router, prefix="/api")
    test_app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(test_app)


def _questions_payload(count: int, source_index: int = 1) -> str:
    return json.dumps(
        {
            "questions": [
                {
                    "text": f"Question {index}: how would you tune the learning rate for this model?",
                    "question_type": "technical" if index % 2 else "conceptual",
                    "difficulty": "medium",
                    "topic": "Gradient Descent",
                    "rationale": "Builds on the candidate's optimisation work.",
                    "source_index": source_index,
                }
                for index in range(1, count + 1)
            ]
        }
    )


@pytest.fixture
def fake_ai(monkeypatch):
    """Capture the prompt the service builds and return canned model output."""
    captured: dict = {"response": _questions_payload(1)}

    def fake_generate(
        client,
        models,
        *,
        contents,
        system_instruction,
        response_schema,
        temperature,
        empty_response_message,
    ):
        captured["prompt"] = contents
        captured["system_instruction"] = system_instruction
        captured["response_schema"] = response_schema
        captured["models"] = models
        response = captured["response"]
        if isinstance(response, Exception):
            raise response
        return models[0], response

    monkeypatch.setattr(question_generator, "generate_json_with_fallback", fake_generate)
    return captured


# --- Generation endpoint ---------------------------------------------------

def test_create_interview_persists_session_and_questions(
    indexed_corpus, candidate, client, fake_ai, db_session
):
    fake_ai["response"] = _questions_payload(3)

    response = client.post(
        "/api/interviews",
        json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": 3},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["candidate_id"] == candidate.id
    assert payload["role"] == "ai-ml-engineer"
    assert payload["role_title"] == "AI/ML Engineer"
    assert len(payload["questions"]) == 3
    assert [question["position"] for question in payload["questions"]] == [1, 2, 3]
    assert payload["focus_skills"]

    stored = db_session.query(InterviewSession).one()
    assert stored.id == payload["session_id"]
    assert stored.candidate_id == candidate.id
    assert db_session.query(Question).count() == 3
    assert stored.candidate.filename == "priya_nair.txt"


def test_generated_questions_are_grounded_in_role_documents(
    indexed_corpus, candidate, client, fake_ai
):
    fake_ai["response"] = _questions_payload(2)

    payload = client.post(
        "/api/interviews",
        json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": 2},
    ).json()

    for question in payload["questions"]:
        assert question["source_document"], "Every question must record its grounding document"
        assert question["source_document"].startswith("ai-ml-engineer/")
        assert question["source_section"]
        assert question["difficulty"] in {"easy", "medium", "hard"}
        assert question["question_type"] in {"technical", "conceptual"}


def test_prompt_includes_candidate_profile_and_retrieved_excerpts(
    indexed_corpus, candidate, client, fake_ai
):
    fake_ai["response"] = _questions_payload(1)

    client.post(
        "/api/interviews",
        json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": 1},
    )

    prompt = fake_ai["prompt"]
    assert "Priya Nair" in prompt
    assert "PyTorch" in prompt
    assert "Churn prediction service" in prompt
    assert "[1] document: ai-ml-engineer/" in prompt
    assert "gradient" in prompt.lower()
    assert "AI/ML Engineer" in prompt
    # The model must be told to ground questions in the supplied excerpts.
    assert "source_index" in fake_ai["system_instruction"]


def test_question_count_is_configurable(indexed_corpus, candidate, client, fake_ai):
    for count in (1, 2, 5):
        fake_ai["response"] = _questions_payload(count)
        response = client.post(
            "/api/interviews",
            json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": count},
        )
        assert response.status_code == 201
        assert len(response.json()["questions"]) == count


def test_question_count_validation_rejects_out_of_range(
    indexed_corpus, candidate, client, fake_ai
):
    for count in (0, 16):
        response = client.post(
            "/api/interviews",
            json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": count},
        )
        assert response.status_code == 422
    assert "prompt" not in fake_ai, "Invalid requests must not reach the model"


def test_unknown_candidate_returns_404(indexed_corpus, client, fake_ai):
    response = client.post(
        "/api/interviews",
        json={"candidate_id": "missing-id", "role": "ai-ml-engineer", "question_count": 2},
    )

    assert response.status_code == 404
    assert "missing-id" in response.json()["detail"]
    assert "prompt" not in fake_ai


def test_unknown_role_returns_400(indexed_corpus, candidate, client, fake_ai):
    response = client.post(
        "/api/interviews",
        json={"candidate_id": candidate.id, "role": "astronaut", "question_count": 2},
    )

    assert response.status_code == 400
    assert "Available roles" in response.json()["detail"]
    assert "ai-ml-engineer" in response.json()["detail"]
    assert "prompt" not in fake_ai


def test_missing_knowledge_base_content_returns_503(vector_store, candidate, client, fake_ai):
    response = client.post(
        "/api/interviews",
        json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": 2},
    )

    assert response.status_code == 503
    assert "ingest_knowledge" in response.json()["detail"]
    assert "prompt" not in fake_ai


def test_missing_api_key_returns_503(indexed_corpus, candidate, client, fake_ai, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    monkeypatch.setattr(get_settings().__class__, "effective_gemini_api_key", "")

    response = client.post(
        "/api/interviews",
        json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": 2},
    )

    assert response.status_code == 503
    assert "GEMINI_API_KEY is not set" in response.json()["detail"]


def test_ai_api_failure_returns_502(indexed_corpus, candidate, client, fake_ai):
    fake_ai["response"] = ServerError(
        503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}}
    )

    response = client.post(
        "/api/interviews",
        json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": 2},
    )

    assert response.status_code == 502
    assert "high demand" in response.json()["detail"]


def test_empty_ai_response_returns_502(indexed_corpus, candidate, client, fake_ai):
    fake_ai["response"] = json.dumps({"questions": []})

    response = client.post(
        "/api/interviews",
        json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": 2},
    )

    assert response.status_code == 502
    assert "no usable grounded questions" in response.json()["detail"]


def test_malformed_ai_json_returns_502(indexed_corpus, candidate, client, fake_ai):
    fake_ai["response"] = "this is not json"

    response = client.post(
        "/api/interviews",
        json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": 2},
    )

    assert response.status_code == 502
    assert "Failed to decode" in response.json()["detail"]


def test_ungrounded_questions_are_dropped(
    indexed_corpus, candidate, client, fake_ai, db_session
):
    payload = json.loads(_questions_payload(3))
    payload["questions"][1]["source_index"] = 99
    fake_ai["response"] = json.dumps(payload)

    response = client.post(
        "/api/interviews",
        json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": 3},
    )

    assert response.status_code == 201
    questions = response.json()["questions"]
    assert len(questions) == 2
    assert [question["position"] for question in questions] == [1, 2]
    assert db_session.query(Question).count() == 2
    assert all(question["source_document"].startswith("ai-ml-engineer/") for question in questions)


def test_duplicate_questions_are_dropped(indexed_corpus, candidate, client, fake_ai):
    payload = json.loads(_questions_payload(2))
    payload["questions"][1]["text"] = payload["questions"][0]["text"]
    fake_ai["response"] = json.dumps(payload)

    response = client.post(
        "/api/interviews",
        json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": 2},
    )

    assert response.status_code == 201
    assert len(response.json()["questions"]) == 1


def test_candidate_without_profile_details_still_gets_role_grounded_questions(
    indexed_corpus, client, fake_ai, db_session
):
    blank = Candidate(
        filename="blank.txt",
        extracted_text="Minimal resume text that contained no parseable profile details.",
        profile_data=CandidateProfile().model_dump(),
    )
    db_session.add(blank)
    db_session.commit()
    db_session.refresh(blank)

    fake_ai["response"] = _questions_payload(2)
    response = client.post(
        "/api/interviews",
        json={"candidate_id": blank.id, "role": "ai-ml-engineer", "question_count": 2},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["focus_skills"] == []
    assert all(
        question["source_document"].startswith("ai-ml-engineer/")
        for question in payload["questions"]
    )
    assert "No structured profile details" in fake_ai["prompt"]


# --- Retrieval endpoint ----------------------------------------------------

def test_get_interview_returns_persisted_questions(indexed_corpus, candidate, client, fake_ai):
    fake_ai["response"] = _questions_payload(3)
    created = client.post(
        "/api/interviews",
        json={"candidate_id": candidate.id, "role": "ai-ml-engineer", "question_count": 3},
    ).json()

    response = client.get(f"/api/interviews/{created['session_id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == created["session_id"]
    assert payload["candidate_id"] == candidate.id
    assert payload["role"] == "ai-ml-engineer"
    assert [question["text"] for question in payload["questions"]] == [
        question["text"] for question in created["questions"]
    ]
    assert [question["position"] for question in payload["questions"]] == [1, 2, 3]


def test_get_unknown_interview_returns_404(client):
    response = client.get("/api/interviews/does-not-exist")

    assert response.status_code == 404
    assert "does-not-exist" in response.json()["detail"]


# --- Service-level behaviour ----------------------------------------------

def test_focus_skills_prefer_role_overlap_then_candidate_extras():
    profile = CandidateProfile(
        programming_languages=["Rust"],
        frameworks_and_tools=["Kubernetes", "PyTorch"],
        technical_skills=["Python", "MLOps"],
    )
    role = get_role("ai-ml-engineer")

    focus = question_generator.candidate_focus_skills(profile, role)

    # Role catalog order wins for overlapping skills, then the candidate's own extras.
    assert focus[:3] == ["Python", "PyTorch", "MLOps"]
    assert "Kubernetes" in focus
    assert len(focus) == len(set(skill.lower() for skill in focus))


def test_service_rejects_non_positive_question_count():
    role = get_role("ai-ml-engineer")

    with pytest.raises(QuestionGenerationError) as exc_info:
        question_generator.generate_interview_questions(CandidateProfile(), role, 0)

    assert exc_info.value.status_code == 400


def test_service_wraps_missing_api_key(indexed_corpus, monkeypatch):
    monkeypatch.setattr(get_settings().__class__, "effective_gemini_api_key", "")
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")

    with pytest.raises(QuestionGenerationError) as exc_info:
        question_generator.generate_interview_questions(
            CandidateProfile(), get_role("ai-ml-engineer"), 2
        )

    assert exc_info.value.status_code == 503
    assert "GEMINI_API_KEY is not set" in exc_info.value.message


def test_service_wraps_empty_ai_response(indexed_corpus, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")

    def raise_empty(*args, **kwargs):
        raise AIResponseError("Gemini returned an empty response during question generation.")

    monkeypatch.setattr(question_generator, "generate_json_with_fallback", raise_empty)

    with pytest.raises(QuestionGenerationError) as exc_info:
        question_generator.generate_interview_questions(
            CandidateProfile(), get_role("ai-ml-engineer"), 2
        )

    assert exc_info.value.status_code == 502
    assert "empty response" in exc_info.value.message
