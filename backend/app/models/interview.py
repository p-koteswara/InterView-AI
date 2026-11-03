"""Interview sessions and their generated questions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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

    def __repr__(self) -> str:
        return f"<Question(session_id={self.session_id}, position={self.position})>"
