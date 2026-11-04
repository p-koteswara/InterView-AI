"""Schemas for answer evaluation, scoring and final interview reports."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

#: Consistent 0-10 score scale used across evaluation criteria and the report.
SCORE_SCALE_MIN = 0.0
SCORE_SCALE_MAX = 10.0


class AnswerEvaluationResult(BaseModel):
    """
    Structured model output for a single answer evaluation.

    The four criterion scores feed the overall answer score; the model never
    judges answers against similarity to a reference text, it assesses technical
    accuracy and accepts valid alternative approaches.
    """

    technical_score: float = Field(
        ge=0.0, le=10.0, description="Technical correctness of the answer (0-10)"
    )
    relevance_score: float = Field(
        ge=0.0, le=10.0, description="How well the answer addresses the question (0-10)"
    )
    depth_score: float = Field(
        ge=0.0, le=10.0, description="Depth and completeness of the answer (0-10)"
    )
    clarity_score: float = Field(
        ge=0.0, le=10.0, description="Clarity of the explanation (0-10)"
    )
    feedback: str = Field(min_length=1, description="Constructive feedback for the candidate")
    improvements: list[str] = Field(
        default_factory=list, description="Suggested ways the answer could improve"
    )

    @field_validator("feedback", mode="before")
    @classmethod
    def _strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("improvements", mode="before")
    @classmethod
    def _normalise_improvements(cls, value):
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned


class AnswerEvaluationResponse(BaseModel):
    """A persisted answer evaluation, embedded in session answers and reports."""

    id: str
    answer_id: str
    session_id: str
    question_id: str
    question_position: int = Field(
        description="Position of the answered question within the session, starting at 1"
    )
    technical_score: float
    relevance_score: float
    depth_score: float
    clarity_score: float
    overall_score: float = Field(
        description="Overall answer score (0-10), the mean of the criterion scores"
    )
    feedback: str
    improvements: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SessionEvaluationsResponse(BaseModel):
    """All evaluations produced for the submitted answers of one session."""

    session_id: str
    total_questions: int = Field(description="Number of questions in the session")
    answered_count: int = Field(description="Number of questions that have an answer")
    evaluated_count: int = Field(description="Number of answers that have an evaluation")
    evaluations: list[AnswerEvaluationResponse] = Field(
        default_factory=list, description="Evaluations ordered by question position"
    )


class FinalReportResult(BaseModel):
    """Structured model output for the final interview report narrative."""

    assessment: str = Field(min_length=1, description="Concise overall assessment of the interview")


class InterviewReportResponse(BaseModel):
    """Final interview report aggregating persisted answer evaluations."""

    id: str
    session_id: str
    candidate_id: str
    candidate_name: str
    role: str
    role_title: str
    interview_date: datetime | None = None
    question_count: int
    answered_count: int
    overall_score: float
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommended_topics: list[str] = Field(default_factory=list)
    assessment: str = Field(default="")
    evaluations: list[AnswerEvaluationResponse] = Field(
        default_factory=list, description="Underlying answer evaluations used for the report"
    )


__all__ = [
    "SCORE_SCALE_MIN",
    "SCORE_SCALE_MAX",
    "AnswerEvaluationResult",
    "AnswerEvaluationResponse",
    "FinalReportResult",
    "InterviewReportResponse",
    "SessionEvaluationsResponse",
]
