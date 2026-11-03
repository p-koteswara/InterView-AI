"""API route controllers."""

from app.api.health import router as health_router
from app.api.resume import router as resume_router

__all__ = ["health_router", "resume_router"]
