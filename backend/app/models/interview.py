"""Interview sessions, their generated questions, and the submitted answers."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewSession(Base):
    """One generated interview for a candidate and a catalog job role."""

    __tablename__ = "interview_sessions"

    id = Column(String(36), primary_key=True, default=_new_id)
    candidate_id = Column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Catalog slug for the role, also the knowledge base directory name.
    role = Column(String(64), nullable=False, index=True)
    role_title = Column(String(128), nullable=False)
    #: Candidate skills that personalisation was anchored on, for auditing.
    focus_skills = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    candidate = relationship("Candidate")
    questions = relationship(
        "Question",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Question.position",
        lazy="selectin",
    )
    answers = relationship(
        "Answer",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    report = relationship(
        "InterviewReport",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<InterviewSession(id={self.id}, role={self.role})>"


class Question(Base):
    """A single generated question, stored with the knowledge chunk that grounds it."""

    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("session_id", "position", name="uq_questions_session_position"),
    )

    id = Column(String(36), primary_key=True, default=_new_id)
    session_id = Column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: 1-based position of the question within its session.
    position = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    #: "technical" (applied design/debug/trade-off) or "conceptual" (why it works).
    question_type = Column(String(32), nullable=False)
    difficulty = Column(String(16), nullable=False)
    topic = Column(String(160), nullable=False)
    rationale = Column(Text, nullable=True)
    #: Provenance of the retrieved chunk the question was grounded in.
    source_document = Column(String(255), nullable=True)
    source_section = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    session = relationship("InterviewSession", back_populates="questions")
    answer = relationship("Answer", back_populates="question", uselist=False)
    def __repr__(self) -> str:
        return f"<Question(session_id={self.session_id}, position={self.position})>"


class Answer(Base):
    """
    A candidate's response to one generated question.

    One answer per question: the unique constraint on ``question_id`` makes
    revisions impossible at the database level rather than only in the API.
    """

    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("question_id", name="uq_answers_question_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_id)
    session_id = Column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        String(36),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answer_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    session = relationship("InterviewSession", back_populates="answers")
    question = relationship("Question", back_populates="answer")
    evaluation = relationship("AnswerEvaluation", back_populates="answer", uselist=False)

    def __repr__(self) -> str:
        return f"<Answer(question_id={self.question_id}, session_id={self.session_id})>"


class AnswerEvaluation(Base):
    """
    AI evaluation of a single submitted answer.

    One evaluation per answer (unique on ``answer_id``); refreshing an answer's
    evaluation is an upsert on the same row.
    """

    __tablename__ = "answer_evaluations"
    __table_args__ = (
        UniqueConstraint("answer_id", name="uq_answer_evaluations_answer_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_id)
    answer_id = Column(
        String(36),
        ForeignKey("answers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    technical_score = Column(Float(4), nullable=False)
    relevance_score = Column(Float(4), nullable=False)
    depth_score = Column(Float(4), nullable=False)
    clarity_score = Column(Float(4), nullable=False)
    overall_score = Column(Float(4), nullable=False)
    feedback = Column(Text, nullable=False)
    improvements = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    answer = relationship("Answer", back_populates="evaluation")

    def __repr__(self) -> str:
        return f"<AnswerEvaluation(id={self.id}, answer_id={self.answer_id})>"


class InterviewReport(Base):
    """
    Final interview report for one completed session.

    Aggregated from the persisted answer evaluations; one report per session.
    """

    __tablename__ = "interview_reports"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_interview_reports_session_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_id)
    session_id = Column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    candidate_id = Column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_name = Column(String(255), nullable=False)
    role = Column(String(64), nullable=False)
    role_title = Column(String(128), nullable=False)
    interview_date = Column(DateTime(timezone=True), nullable=True)
    question_count = Column(Integer, nullable=False)
    answered_count = Column(Integer, nullable=False)
    overall_score = Column(Float(4), nullable=False)
    strengths = Column(JSON, nullable=False, default=list)
    weaknesses = Column(JSON, nullable=False, default=list)
    recommended_topics = Column(JSON, nullable=False, default=list)
    assessment = Column(Text, nullable=False, default="")

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    session = relationship("InterviewSession", back_populates="report")

    def __repr__(self) -> str:
        return f"<InterviewReport(id={self.id}, session_id={self.session_id})>"
