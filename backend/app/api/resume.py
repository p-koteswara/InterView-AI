import logging
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.candidate import Candidate
from app.schemas.resume import CandidateProfile, ResumeUploadResponse
from app.services.profile_extractor import (
    ProfileExtractionError,
    extract_candidate_profile,
)
from app.services.resume_parser import ResumeParsingError, parse_resume_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resume", tags=["resume"])


@router.post(
    "/upload",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and parse a candidate resume",
    description="Accepts a PDF or TXT file, extracts readable text using PyMuPDF, invokes Gemini AI for structured profile extraction, and stores the record in SQLite.",
)
def upload_resume(
    file: UploadFile = File(..., description="Resume file in PDF or TXT format"),
    db: Session = Depends(get_db),
) -> ResumeUploadResponse:
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid file must be provided.",
        )

    filename = file.filename
    logger.info("Received resume upload: %s (content_type=%s)", filename, file.content_type)

    try:
        content = file.file.read()
    except Exception as exc:
        logger.exception("Failed to read uploaded file stream: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read the uploaded file stream.",
        ) from exc

    # Step 1: Text extraction & validation
    try:
        extracted_text, _ = parse_resume_file(filename=filename, content=content)
    except ResumeParsingError as exc:
        logger.warning("Resume parsing error for '%s': %s", filename, exc.message)
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc

    # Step 2: AI Candidate Profile Extraction
    try:
        profile = extract_candidate_profile(extracted_text)
    except ProfileExtractionError as exc:
        logger.error("AI profile extraction failed for '%s': %s", filename, exc.message)
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc

    # Step 3: Database Persistence
    try:
        candidate = Candidate(
            filename=filename,
            extracted_text=extracted_text,
            profile_data=profile.model_dump(),
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        logger.info("Persisted candidate profile with ID: %s", candidate.id)
    except Exception as exc:
        db.rollback()
        logger.exception("Database error persisting candidate profile: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database failure while saving candidate profile.",
        ) from exc

    return ResumeUploadResponse(
        candidate_id=candidate.id,
        filename=candidate.filename,
        extracted_text=candidate.extracted_text,
        profile=profile,
        created_at=candidate.created_at,
    )


@router.get(
    "/{candidate_id}",
    response_model=ResumeUploadResponse,
    summary="Get candidate profile by ID",
    description="Retrieves a candidate's stored profile and extracted resume text.",
)
def get_candidate(candidate_id: str, db: Session = Depends(get_db)) -> ResumeUploadResponse:
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate with ID '{candidate_id}' not found.",
        )

    profile = CandidateProfile.model_validate(candidate.profile_data)
    return ResumeUploadResponse(
        candidate_id=candidate.id,
        filename=candidate.filename,
        extracted_text=candidate.extracted_text,
        profile=profile,
        created_at=candidate.created_at,
    )
