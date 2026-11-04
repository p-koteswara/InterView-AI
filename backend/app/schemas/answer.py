"""Schemas for answer submission and retrieval."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

#: Upper bound on a single answer, high enough for a long spoken-style response.
MAX_ANSWER_LENGTH = 20000


class AnswerSubmitRequest(BaseModel):
    """Request to record the candidate's answer to one interview question."""

    answer_text: str = Field(
        min_length=1,
        max_length=MAX_ANSWER_LENGTH,
        description=f"The candidate's answer ({MAX_ANSWER_LENGTH} characters maximum)",
    )

    @field_validator("answer_text", mode="before")
    @classmethod
    def _require_content(cls, value):
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            raise ValueError("Answer text cannot be empty.")
        return text


class AnswerResponse(BaseModel):
    """A stored answer, identified against its question within the session."""

    id: str
    session_id: str
    question_id: str
    question_position: int = Field(
        description="Position of the answered question within the session, starting at 1"
    )
    answer_text: str
    created_at: datetime
    updated_at: datetime


class SessionAnswersResponse(BaseModel):
    """All answers submitted so far for one interview session."""

    session_id: str
    total_questions: int = Field(description="Number of questions in the session")
    answered_count: int = Field(description="Number of questions that have an answer")
    answers: list[AnswerResponse] = Field(
        default_factory=list, description="Answers ordered by question position"
    )
