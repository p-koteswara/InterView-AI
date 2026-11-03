import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, JSON

from app.database.base import Base


class Candidate(Base):
    """Stores candidate resume data and structured extracted profiles."""

    __tablename__ = "candidates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    extracted_text = Column(Text, nullable=False)
    profile_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<Candidate(id={self.id}, filename={self.filename})>"
