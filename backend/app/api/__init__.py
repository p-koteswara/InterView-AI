"""API route controllers."""

from app.api.evaluations import router as evaluations_router
from app.api.health import router as health_router
from app.api.interview import router as interview_router
from app.api.resume import router as resume_router
from app.api.roles import router as roles_router

__all__ = [
    "evaluations_router",
    "health_router",
    "interview_router",
    "resume_router",
    "roles_router",
]
