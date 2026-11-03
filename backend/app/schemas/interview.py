"""Schemas for interview generation requests, AI output and API responses."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

QuestionType = Literal["technical", "conceptual"]
DifficultyLevel = Literal["easy", "medium", "hard"]

#: Default number of questions in a generated interview.
DEFAULT_QUESTION_COUNT = 6


class InterviewCreateRequest(BaseModel):
    """Request to generate an interview for an existing candidate."""

    candidate_id: str = Field(
        min_length=1,
        description="ID of the candidate whose stored resume profile personalises the interview",
    )
    role: str = Field(
        min_length=1,
        description="Job role slug from GET /api/roles (e.g. 'backend-engineer')",
    )
    question_count: int = Field(
        default=DEFAULT_QUESTION_COUNT,
        ge=1,
        le=15,
        description="Number of questions to generate (1-15)",
    )


class GeneratedQuestion(BaseModel):
    """
    A question as returned by the model.

    ``source_index`` is the 1-based number of the knowledge excerpt that
    grounds the question; it is resolved to a document and section before the
    question is persisted, so hallucinated citations can be rejected.
    """

    text: str = Field(description="The interview question, phrased for a spoken interview")
    question_type: QuestionType = Field(
        description="'technical' for applied design/debug/trade-off questions, "
        "'conceptual' for why-it-works and when-it-fails questions"
    )
    difficulty: DifficultyLevel = Field(description="Difficulty calibrated to the candidate")
    topic: str = Field(description="Short topic or category label, e.g. 'Gradient Descent'")
    rationale: str = Field(description="One sentence on why this question suits this candidate")
    source_index: int = Field(
        ge=1,
        description="1-based index of the knowledge excerpt that grounds this question",
    )

    @field_validator("text", "topic", "rationale", mode="before")
    @classmethod
    def _strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("question_type", "difficulty", mode="before")
    @classmethod
    def _normalise_enum(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class GeneratedInterview(BaseModel):
    """Structured model output for one interview."""

    questions: list[GeneratedQuestion] = Field(
        default_factory=list, description="Generated questions, in intended interview order"
    )


class QuestionResponse(BaseModel):
    """A persisted question, including the knowledge chunk that grounds it."""

    id: str
    position: int
    text: str
    question_type: QuestionType
    difficulty: DifficultyLevel
    topic: str
    rationale: str | None = None
    source_document: str | None = Field(
        default=None, description="Knowledge base document the question was grounded in"
    )
    source_section: str | None = Field(
        default=None, description="Section heading within that document"
    )


class InterviewSessionResponse(BaseModel):
    """A generated interview session with all of its questions."""

    session_id: str
    candidate_id: str
    role: str
    role_title: str
    focus_skills: list[str] = Field(
        default_factory=list, description="Candidate skills used to personalise the questions"
    )
    created_at: datetime
    questions: list[QuestionResponse]
