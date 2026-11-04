"""REST endpoints for AI answer evaluation and final interview reports."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.job_roles import get_role, role_slugs
from app.database.session import get_db
from app.models.candidate import Candidate
from app.models.interview import Answer, AnswerEvaluation, InterviewReport, InterviewSession, Question
from app.schemas.evaluation import (
    AnswerEvaluationResponse,
    InterviewReportResponse,
    SessionEvaluationsResponse,
)
from app.schemas.resume import CandidateProfile
from app.services.evaluation import (
    AnswerEvaluation as AnswerEvaluationModel,
    EvaluationError,
    generate_report,
    evaluate_answer,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/interviews", tags=["evaluations"])


def _as_utc(value) -> datetime:
    """SQLite drops timezone information; every stored timestamp is written in UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _candidate_name(candidate: Candidate) -> str:
    profile_data = candidate.profile_data or {}
    return str(profile_data.get("name") or candidate.filename or "Unknown Candidate")


def _serialize_answer_evaluation(
    evaluation: AnswerEvaluation,
    answer_id: str,
    question_position: int,
    session_id: str,
) -> AnswerEvaluationResponse:
    """Map a stored answer evaluation onto the API response shape."""
    return AnswerEvaluationResponse(
        id=evaluation.id,
        answer_id=answer_id,
        session_id=session_id,
        question_id=evaluation.answer.question_id,
        question_position=question_position,
        technical_score=evaluation.technical_score,
        relevance_score=evaluation.relevance_score,
        depth_score=evaluation.depth_score,
        clarity_score=evaluation.clarity_score,
        overall_score=evaluation.overall_score,
        feedback=evaluation.feedback,
        improvements=list(evaluation.improvements or []),
        created_at=_as_utc(evaluation.created_at),
        updated_at=_as_utc(evaluation.updated_at),
    )


def _serialize_report(
    report: InterviewReport,
    evaluations: list[AnswerEvaluation],
) -> InterviewReportResponse:
    """Map a stored interview report plus its evaluations onto the API response."""
    ordered = sorted(evaluations, key=lambda e: e.answer.question.position)
    return InterviewReportResponse(
        id=report.id,
        session_id=report.session_id,
        candidate_id=report.candidate_id,
        candidate_name=report.candidate_name,
        role=report.role,
        role_title=report.role_title,
        interview_date=report.interview_date,
        question_count=report.question_count,
        answered_count=report.answered_count,
        overall_score=report.overall_score,
        strengths=list(report.strengths or []),
        weaknesses=list(report.weaknesses or []),
        recommended_topics=list(report.recommended_topics or []),
        assessment=report.assessment or "",
        evaluations=[
            AnswerEvaluationResponse(
                id=evaluation.id,
                answer_id=evaluation.answer_id,
                session_id=report.session_id,
                question_id=evaluation.answer.question_id,
                question_position=evaluation.answer.question.position,
                technical_score=evaluation.technical_score,
                relevance_score=evaluation.relevance_score,
                depth_score=evaluation.depth_score,
                clarity_score=evaluation.clarity_score,
                overall_score=evaluation.overall_score,
                feedback=evaluation.feedback,
                improvements=list(evaluation.improvements or []),
                created_at=_as_utc(evaluation.created_at),
                updated_at=_as_utc(evaluation.updated_at),
            )
            for evaluation in ordered
        ],
    )


def _get_session_or_404(db: Session, session_id: str) -> InterviewSession:
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interview session with ID '{session_id}' not found.",
        )
    return session


@router.post(
    "/{session_id}/evaluations",
    response_model=SessionEvaluationsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate all submitted answers for one interview session",
    description=(
        "Runs the AI answer evaluation for every submitted answer of the session and "
        "persists the evaluations. Existing evaluations are refreshed."
    ),
)
def evaluate_interview_answers(
    session_id: str,
    db: Session = Depends(get_db),
) -> SessionEvaluationsResponse:
    session = _get_session_or_404(db, session_id)
    candidate: Candidate = session.candidate
    role = get_role(session.role)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown job role '{session.role}'. Available roles: {', '.join(role_slugs())}.",
        )

    try:
        profile = CandidateProfile.model_validate(candidate.profile_data or {})
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The stored candidate profile could not be read.",
        ) from exc

    answers = (
        db.query(Answer)
        .join(Question, Answer.question_id == Question.id)
        .filter(Answer.session_id == session_id)
        .order_by(Question.position)
        .all()
    )

    evaluations: list[AnswerEvaluationModel] = []
    for answer in answers:
        evaluation = evaluate_answer(profile, role, answer.question, answer.answer_text)
        existing = (
            db.query(AnswerEvaluation).filter(AnswerEvaluation.answer_id == answer.id).first()
        )
        if existing is None:
            db.add(
                AnswerEvaluation(
                    answer_id=answer.id,
                    technical_score=evaluation.technical_score,
                    relevance_score=evaluation.relevance_score,
                    depth_score=evaluation.depth_score,
                    clarity_score=evaluation.clarity_score,
                    overall_score=evaluation.overall_score,
                    feedback=evaluation.feedback,
                    improvements=evaluation.improvements,
                )
            )
        else:
            # Refresh an existing evaluation so re-runs pick up corrected answers.
            existing.technical_score = evaluation.technical_score
            existing.relevance_score = evaluation.relevance_score
            existing.depth_score = evaluation.depth_score
            existing.clarity_score = evaluation.clarity_score
            existing.overall_score = evaluation.overall_score
            existing.feedback = evaluation.feedback
            existing.improvements = evaluation.improvements
            existing.updated_at = _as_utc(datetime.now(timezone.utc))
        evaluations.append(evaluation)

    db.flush()

    persisted = (
        db.query(AnswerEvaluation)
        .join(AnswerEvaluation.answer)
        .filter(AnswerEvaluation.answer.has(session_id=session_id))
        .all()
    )
    responses = [
        _serialize_answer_evaluation(
            evaluation,
            evaluation.answer_id,
            evaluation.answer.question.position,
            session_id,
        )
        for evaluation in sorted(persisted, key=lambda e: e.answer.question.position)
    ]

    return SessionEvaluationsResponse(
        session_id=session_id,
        total_questions=len(session.questions),
        answered_count=len(answers),
        evaluated_count=len(responses),
        evaluations=responses,
    )


@router.get(
    "/{session_id}/evaluations",
    response_model=SessionEvaluationsResponse,
    summary="Retrieve the evaluations for one interview session",
    description=(
        "Returns the persisted answer evaluations for every submitted answer, ordered by "
        "question position. Empty when no evaluation has been produced yet."
    ),
)
def get_interview_evaluations(
    session_id: str,
    db: Session = Depends(get_db),
) -> SessionEvaluationsResponse:
    session = _get_session_or_404(db, session_id)

    evaluations = (
        db.query(AnswerEvaluation)
        .join(AnswerEvaluation.answer)
        .filter(AnswerEvaluation.answer.has(session_id=session_id))
        .all()
    )
    responses = [
        _serialize_answer_evaluation(
            evaluation,
            evaluation.answer_id,
            evaluation.answer.question.position,
            session_id,
        )
        for evaluation in sorted(evaluations, key=lambda e: e.answer.question.position)
    ]

    return SessionEvaluationsResponse(
        session_id=session_id,
        total_questions=len(session.questions),
        answered_count=len(session.answers),
        evaluated_count=len(responses),
        evaluations=responses,
    )


@router.post(
    "/{session_id}/report",
    response_model=InterviewReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate the final interview report",
    description=(
        "Aggregates the persisted answer evaluations into the final interview report "
        "(overall score, strengths, weaknesses, recommended topics, assessment). "
        "Existing reports are returned when ``force`` is not set."
    ),
)
def generate_interview_report(
    session_id: str,
    db: Session = Depends(get_db),
    force: bool = False,
) -> InterviewReportResponse:
    session = _get_session_or_404(db, session_id)
    candidate: Candidate = session.candidate
    role = get_role(session.role)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown job role '{session.role}'. Available roles: {', '.join(role_slugs())}.",
        )

    existing_report = (
        db.query(InterviewReport).filter(InterviewReport.session_id == session_id).first()
    )
    if existing_report is not None and not force:
        evaluations = (
            db.query(AnswerEvaluation)
            .join(AnswerEvaluation.answer)
            .filter(AnswerEvaluation.answer.has(session_id=session_id))
            .all()
        )
        return _serialize_report(existing_report, evaluations)

    evaluations = (
        db.query(AnswerEvaluation)
        .join(AnswerEvaluation.answer)
        .filter(AnswerEvaluation.answer.has(session_id=session_id))
        .all()
    )
    if not evaluations:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot generate a final report without answer evaluations. Submit answers first.",
        )

    evaluated_models = [
        AnswerEvaluationModel(
            technical_score=evaluation.technical_score,
            relevance_score=evaluation.relevance_score,
            depth_score=evaluation.depth_score,
            clarity_score=evaluation.clarity_score,
            overall_score=evaluation.overall_score,
            feedback=evaluation.feedback,
            improvements=list(evaluation.improvements or []),
            topic=evaluation.answer.question.topic or "",
        )
        for evaluation in evaluations
    ]

    try:
        result = generate_report(
            candidate_name=_candidate_name(candidate),
            role=role,
            question_count=len(session.questions),
            evaluations=evaluated_models,
        )
    except EvaluationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    interview_date = (
        _as_utc(max((answer.created_at for answer in session.answers), default=None))
        if session.answers
        else _as_utc(session.created_at)
    )
    report = InterviewReport(
        session_id=session.id,
        candidate_id=candidate.id,
        candidate_name=_candidate_name(candidate),
        role=session.role,
        role_title=session.role_title,
        interview_date=interview_date,
        question_count=len(session.questions),
        answered_count=len(session.answers),
        overall_score=result.overall_score,
        strengths=result.strengths,
        weaknesses=result.weaknesses,
        recommended_topics=result.recommended_topics,
        assessment=result.assessment,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    persisted_evaluations = (
        db.query(AnswerEvaluation)
        .join(AnswerEvaluation.answer)
        .filter(AnswerEvaluation.answer.has(session_id=session_id))
        .all()
    )
    return _serialize_report(report, persisted_evaluations)


@router.get(
    "/{session_id}/report",
    response_model=InterviewReportResponse,
    summary="Retrieve an existing interview report",
    description=(
        "Returns the final interview report previously generated for the session, "
        "together with the answer evaluations it aggregates."
    ),
)
def get_interview_report(
    session_id: str,
    db: Session = Depends(get_db),
) -> InterviewReportResponse:
    report = (
        db.query(InterviewReport).filter(InterviewReport.session_id == session_id).first()
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interview report for session ID '{session_id}' was not found.",
        )

    evaluations = (
        db.query(AnswerEvaluation)
        .join(AnswerEvaluation.answer)
        .filter(AnswerEvaluation.answer.has(session_id=session_id))
        .all()
    )
    return _serialize_report(report, evaluations)
