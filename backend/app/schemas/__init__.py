"""Pydantic schemas for request and response validation."""

from app.schemas.answer import (
    MAX_ANSWER_LENGTH,
    AnswerResponse,
    AnswerSubmitRequest,
    SessionAnswersResponse,
)
from app.schemas.evaluation import (
    AnswerEvaluationResponse,
    FinalReportResult,
    InterviewReportResponse,
    SessionEvaluationsResponse,
)
from app.schemas.health import HealthResponse
from app.schemas.interview import (
    DifficultyLevel,
    GeneratedInterview,
    GeneratedQuestion,
    InterviewCreateRequest,
    InterviewSessionResponse,
    QuestionResponse,
    QuestionType,
)
from app.schemas.roles import JobRoleResponse, RoleCatalogResponse
from app.schemas.resume import (
    CandidateProfile,
    EducationItem,
    ExperienceItem,
    ProjectItem,
    ResumeUploadResponse,
)

__all__ = [
    "HealthResponse",
    "DifficultyLevel",
    "GeneratedInterview",
    "GeneratedQuestion",
    "InterviewCreateRequest",
    "InterviewSessionResponse",
    "QuestionResponse",
    "QuestionType",
    "JobRoleResponse",
    "RoleCatalogResponse",
    "CandidateProfile",
    "EducationItem",
    "ExperienceItem",
    "ProjectItem",
    "ResumeUploadResponse",
    "MAX_ANSWER_LENGTH",
    "AnswerResponse",
    "AnswerSubmitRequest",
    "SessionAnswersResponse",
    "AnswerEvaluationResponse",
    "FinalReportResult",
    "InterviewReportResponse",
    "SessionEvaluationsResponse",
]
