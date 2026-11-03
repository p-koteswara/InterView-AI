import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.health import router as health_router
from app.api.interview import router as interview_router
from app.api.resume import router as resume_router
from app.api.roles import router as roles_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.database.session import init_db
import app.models  # Ensures all ORM models are registered with Base metadata before init_db()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    init_db()
    logger.info("Starting %s (%s)", settings.app_name, settings.environment)
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description="Candidate Screening and AI Interview Platform API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, StarletteHTTPException):
            detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
            return JSONResponse(status_code=exc.status_code, content={"detail": detail})
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(health_router, prefix="/api")
    app.include_router(resume_router, prefix="/api")
    app.include_router(roles_router, prefix="/api")
    app.include_router(interview_router, prefix="/api")
    return app


app = create_app()
