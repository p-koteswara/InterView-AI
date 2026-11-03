import io
import json
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf
import pytest
from fastapi import HTTPException, UploadFile
from google.genai.errors import ClientError, ServerError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.resume import get_candidate, upload_resume
from app.core.config import get_settings
from app.database.base import Base
from app.models.candidate import Candidate
from app.schemas.resume import CandidateProfile, EducationItem, ExperienceItem, ProjectItem
from app.services.profile_extractor import ProfileExtractionError, extract_candidate_profile
from app.services.resume_parser import (
    ResumeParsingError,
    extract_text_from_pdf,
    extract_text_from_txt,
    parse_resume_file,
    validate_file_metadata,
)

# In-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def create_sample_pdf(text: str) -> bytes:
    """Helper to generate valid in-memory PDF bytes containing text."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# --- Parser Unit Tests ---

def test_validate_file_metadata_valid():
    assert validate_file_metadata("resume.pdf", 1024) == ".pdf"
    assert validate_file_metadata("RESUME.TXT", 2048) == ".txt"


def test_validate_file_metadata_invalid_extension():
    with pytest.raises(ResumeParsingError) as exc_info:
        validate_file_metadata("resume.png", 1024)
    assert "Unsupported file format" in exc_info.value.message


def test_validate_file_metadata_empty_file():
    with pytest.raises(ResumeParsingError) as exc_info:
        validate_file_metadata("resume.pdf", 0)
    assert "The uploaded file is empty" in exc_info.value.message


def test_validate_file_metadata_oversized():
    with pytest.raises(ResumeParsingError) as exc_info:
        validate_file_metadata("resume.pdf", 11 * 1024 * 1024)
    assert "exceeds the 10 MB limit" in exc_info.value.message


def test_extract_text_from_pdf_valid():
    content = "Jane Doe\nSenior Backend Engineer\nPython, FastAPI, PostgreSQL, Docker"
    pdf_bytes = create_sample_pdf(content)
    extracted = extract_text_from_pdf(pdf_bytes)
    assert "Jane Doe" in extracted
    assert "FastAPI" in extracted


def test_extract_text_from_pdf_corrupted():
    with pytest.raises(ResumeParsingError) as exc_info:
        extract_text_from_pdf(b"not a valid pdf header")
    assert "corrupted, encrypted, or cannot be opened" in exc_info.value.message


def test_extract_text_from_txt_valid():
    raw_text = "John Smith\nMachine Learning Engineer\nPyTorch, TensorFlow, Scikit-Learn"
    extracted = extract_text_from_txt(raw_text.encode("utf-8"))
    assert "John Smith" in extracted
    assert "PyTorch" in extracted


def test_parse_resume_file_too_short():
    with pytest.raises(ResumeParsingError) as exc_info:
        parse_resume_file("short.txt", b"Too brief")
    assert "too brief" in exc_info.value.message


# --- Endpoint Integration Tests ---

def test_upload_invalid_extension(db_session):
    upload = UploadFile(file=io.BytesIO(b"fake image data"), filename="photo.png")
    with pytest.raises(HTTPException) as exc_info:
        upload_resume(file=upload, db=db_session)
    assert exc_info.value.status_code == 400
    assert "Unsupported file format" in exc_info.value.detail


def test_upload_empty_file(db_session):
    upload = UploadFile(file=io.BytesIO(b""), filename="empty.pdf")
    with pytest.raises(HTTPException) as exc_info:
        upload_resume(file=upload, db=db_session)
    assert exc_info.value.status_code == 400
    assert "The uploaded file is empty" in exc_info.value.detail


def test_upload_corrupted_pdf(db_session):
    upload = UploadFile(file=io.BytesIO(b"corrupted header"), filename="corrupt.pdf")
    with pytest.raises(HTTPException) as exc_info:
        upload_resume(file=upload, db=db_session)
    assert exc_info.value.status_code == 400
    assert "corrupted" in exc_info.value.detail.lower()


def test_upload_gemini_api_key_missing(db_session):
    sample_text = (
        "Alice Smith\nSoftware Engineer\nExperience: 5 years building scalable web backends with Python."
    )
    upload = UploadFile(
        file=io.BytesIO(sample_text.encode("utf-8")),
        filename="resume.txt",
    )
    with patch("app.core.config.Settings.effective_gemini_api_key", ""):
        with pytest.raises(HTTPException) as exc_info:
            upload_resume(file=upload, db=db_session)
    assert exc_info.value.status_code == 503
    assert "GEMINI_API_KEY is not set" in exc_info.value.detail


def test_upload_valid_resume_with_mocked_gemini(db_session):
    sample_text = (
        "Alex Rivera\nEmail: alex@example.com\nPhone: +1-555-0199\n"
        "Education: B.S. in Computer Science, Stanford University (2020)\n"
        "Experience: Senior Backend Engineer at TechCorp (2020 - Present)\n"
        "Skills: Python, Go, FastAPI, Docker, Kubernetes, PostgreSQL"
    )
    pdf_bytes = create_sample_pdf(sample_text)
    upload = UploadFile(
        file=io.BytesIO(pdf_bytes),
        filename="alex_rivera_resume.pdf",
    )

    mock_profile = CandidateProfile(
        name="Alex Rivera",
        email="alex@example.com",
        phone="+1-555-0199",
        location="California, USA",
        education=[
            EducationItem(
                institution="Stanford University",
                degree="B.S.",
                field_of_study="Computer Science",
                end_year="2020",
            )
        ],
        work_experience=[
            ExperienceItem(
                company="TechCorp",
                role="Senior Backend Engineer",
                duration="2020 - Present",
                description=["Built scalable cloud microservices"],
            )
        ],
        technical_skills=["Microservices", "Cloud Architecture"],
        programming_languages=["Python", "Go"],
        frameworks_and_tools=["FastAPI", "Docker", "Kubernetes", "PostgreSQL"],
        projects=[
            ProjectItem(
                title="Distributed Task Queue",
                description="High throughput task processing system",
                technologies=["Go", "Redis"],
            )
        ],
        certifications=["AWS Certified Solutions Architect"],
        relevant_domains=["Backend Engineering", "Distributed Systems"],
    )

    with patch("app.api.resume.extract_candidate_profile", return_value=mock_profile):
        response = upload_resume(file=upload, db=db_session)

    assert response.filename == "alex_rivera_resume.pdf"
    assert "Alex Rivera" in response.extracted_text
    assert response.profile.name == "Alex Rivera"
    assert response.profile.email == "alex@example.com"
    assert "Python" in response.profile.programming_languages
    assert "FastAPI" in response.profile.frameworks_and_tools
    assert response.candidate_id is not None

    # Verify retrieval via get_candidate
    fetched = get_candidate(candidate_id=response.candidate_id, db=db_session)
    assert fetched.candidate_id == response.candidate_id
    assert fetched.profile.name == "Alex Rivera"
    assert fetched.profile.email == "alex@example.com"


def test_get_candidate_not_found(db_session):
    with pytest.raises(HTTPException) as exc_info:
        get_candidate(candidate_id="non-existent-id", db=db_session)
    assert exc_info.value.status_code == 404


# --- Model Selection & Fallback Tests ---

SAMPLE_RESUME_TEXT = (
    "Jane Doe\nBackend engineer with five years of Python and FastAPI experience."
)


def _stub_text_response(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(text=json.dumps(payload))


def _generate_content_stub(behaviours):
    """Build a generate_content side effect; behaviours maps model name -> payload or exception."""
    calls: list[str] = []

    def fake_generate_content(model, contents, config):
        calls.append(model)
        behaviour = behaviours[model]
        if isinstance(behaviour, Exception):
            raise behaviour
        return _stub_text_response(behaviour)

    return fake_generate_content, calls


def test_model_candidates_come_from_settings():
    settings = get_settings()
    candidates = settings.gemini_model_candidates
    assert candidates[0] == settings.gemini_model
    assert candidates[-1] == settings.gemini_fallback_model
    assert len(candidates) == len(set(candidates))


def test_extraction_falls_back_on_transient_model_error():
    primary, fallback = get_settings().gemini_model_candidates[:2]
    fake_generate, calls = _generate_content_stub(
        {
            primary: ServerError(
                503,
                {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}},
            ),
            fallback: {"name": "Fallback Candidate", "programming_languages": ["Python"]},
        }
    )

    with patch("app.core.config.Settings.effective_gemini_api_key", "test-key"), patch(
        "app.services.profile_extractor.genai.Client"
    ) as client_cls:
        client_cls.return_value.models.generate_content.side_effect = fake_generate
        profile = extract_candidate_profile(SAMPLE_RESUME_TEXT)

    assert profile.name == "Fallback Candidate"
    assert calls == [primary, fallback]


def test_extraction_does_not_fall_back_on_permanent_error():
    primary = get_settings().gemini_model_candidates[0]
    fake_generate, calls = _generate_content_stub(
        {
            primary: ClientError(
                404,
                {"error": {"code": 404, "message": "model not found", "status": "NOT_FOUND"}},
            )
        }
    )

    with patch("app.core.config.Settings.effective_gemini_api_key", "test-key"), patch(
        "app.services.profile_extractor.genai.Client"
    ) as client_cls:
        client_cls.return_value.models.generate_content.side_effect = fake_generate
        with pytest.raises(ProfileExtractionError) as exc_info:
            extract_candidate_profile(SAMPLE_RESUME_TEXT)

    assert exc_info.value.status_code == 502
    assert "model not found" in exc_info.value.message
    assert calls == [primary]


def test_extraction_reports_failure_when_all_models_unavailable():
    candidates = get_settings().gemini_model_candidates
    fake_generate, calls = _generate_content_stub(
        {
            model: ServerError(
                503,
                {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}},
            )
            for model in candidates
        }
    )

    with patch("app.core.config.Settings.effective_gemini_api_key", "test-key"), patch(
        "app.services.profile_extractor.genai.Client"
    ) as client_cls:
        client_cls.return_value.models.generate_content.side_effect = fake_generate
        with pytest.raises(ProfileExtractionError) as exc_info:
            extract_candidate_profile(SAMPLE_RESUME_TEXT)

    assert exc_info.value.status_code == 502
    assert "high demand" in exc_info.value.message
    assert calls == candidates
