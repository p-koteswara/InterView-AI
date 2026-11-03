import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.job_roles import get_role, role_slugs
from app.database.session import get_db
from app.models.candidate import Candidate
from app.models.interview import InterviewSession, Question
from app.schemas.interview import (
    InterviewCreateRequest,
    InterviewSessionResponse,
    QuestionResponse,
)
from app.schemas.resume import CandidateProfile
from app.services.question_generator import (
    QuestionGenerationError,
    generate_interview_questions,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/interviews", tags=["interviews"])


def _serialize(session: InterviewSession) -> InterviewSessionResponse:
    """Map a persisted session and its questions onto the API response."""
    return InterviewSessionResponse(
        session_id=session.id,
        candidate_id=session.candidate_id,
        role=session.role,
        role_title=session.role_title,
        focus_skills=list(session.focus_skills or []),
        created_at=session.created_at,
        questions=[
            QuestionResponse(
                id=question.id,
                position=question.position,
                text=question.text,
                question_type=question.question_type,
                difficulty=question.difficulty,
                topic=question.topic,
                rationale=question.rationale,
                source_document=question.source_document,
                source_section=question.source_section,
            )
            for question in session.questions
        ],
    )


@router.post(
    "",
    response_model=InterviewSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate an interview for a candidate and role",
    description=(
        "Retrieves role-scoped knowledge base chunks, personalises questions using the "
        "candidate's stored resume profile, generates a balanced set of technical and "
        "conceptual questions with difficulty levels, and persists the session."
    ),
)
def create_interview(
    payload: InterviewCreateRequest,
    db: Session = Depends(get_db),
) -> InterviewSessionResponse:
    candidate = db.get(Candidate, payload.candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate with ID '{payload.candidate_id}' not found.",
        )

    role = get_role(payload.role.strip())
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown job role '{payload.role}'. "
                f"Available roles: {', '.join(role_slugs())}."
            ),
        )

    try:
        profile = CandidateProfile.model_validate(candidate.profile_data or {})
    except ValidationError as exc:
        logger.exception("Stored profile for candidate %s is not readable: %s", candidate.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The stored candidate profile could not be read.",
        ) from exc

    try:
        result = generate_interview_questions(profile, role, payload.question_count)
    except QuestionGenerationError as exc:
        logger.error(
            "Interview generation failed for candidate %s (role=%s): %s",
            candidate.id,
            role.slug,
            exc.message,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    session = InterviewSession(
        candidate_id=candidate.id,
        role=role.slug,
        role_title=role.title,
        focus_skills=result.focus_skills,
    )
    session.questions = [
        Question(
            position=position,
            text=draft.text,
            question_type=draft.question_type,
            difficulty=draft.difficulty,
            topic=draft.topic,
            rationale=draft.rationale,
            source_document=draft.source_document,
            source_section=draft.source_section,
        )
        for position, draft in enumerate(result.questions, start=1)
    ]

    try:
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info(
            "Persisted interview session %s with %d question(s) for candidate %s",
            session.id,
            len(result.questions),
            candidate.id,
        )
    except Exception as exc:
        db.rollback()
        logger.exception("Database error persisting interview session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database failure while saving the interview session.",
        ) from exc

    return _serialize(session)


@router.get(
    "/{session_id}",
    response_model=InterviewSessionResponse,
    summary="Get an interview session and its questions",
    description="Retrieves a previously generated interview session with all persisted questions.",
)
def get_interview(
    session_id: str,
    db: Session = Depends(get_db),
) -> InterviewSessionResponse:
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interview session with ID '{session_id}' not found.",
        )

    return _serialize(session)
