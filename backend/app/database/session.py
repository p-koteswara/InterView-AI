from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.database.base import Base

settings = get_settings()

connect_args = (
    {"check_same_thread": False} if settings.resolved_database_url.startswith("sqlite") else {}
)
engine = create_engine(settings.resolved_database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """Provide a transactional database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables for registered SQLAlchemy models."""
    Base.metadata.create_all(bind=engine)
