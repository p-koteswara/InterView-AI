"""AI-powered answer evaluation and final interview reporting."""

import json
import logging
from dataclasses import dataclass, field

from google import genai
from google.genai.errors import APIError
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.job_roles import JobRole
from app.schemas.evaluation import AnswerEvaluationResult, FinalReportResult
from app.schemas.resume import CandidateProfile
from app.services.gemini_client import (
    AIResponseError,
    generate_json_with_fallback,
    strip_json_fences,
)
from app.services.rag import retrieval
from app.services.rag.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

#: Maximum excerpts handed to the evaluator in one prompt.
MAX_CONTEXT_CHUNKS = 4

#: Rough character budget for retrieved context, keeping evaluation prompts cheap.
MAX_CONTEXT_CHARS = 9000

#: How many answers an interview must have before a final report can be produced.
MIN_ANSWERS_FOR_REPORT = 1

EVALUATION_SYSTEM_INSTRUCTION = """
You are a senior technical interviewer evaluating a candidate's spoken answer.

Evaluation rules:
1. Assess technical accuracy, not similarity to the reference text. Accept valid
   alternative approaches and explanations when the underlying concept is correct.
2. Score each dimension from 0 to 10:
   - technical_score: correctness of the technical content.
   - relevance_score: how fully the answer addresses the question.
   - depth_score: depth and completeness of the reasoning.
   - clarity_score: clarity of the explanation.
3. The overall answer score is the mean of the four criterion scores.
4. Write feedback that explains what was correct, what was missing, and how the
   answer could improve. Put concrete improvement suggestions in ``improvements``.
5. Do not hallucinate corrections that are not supported by the reference material.
6. If the reference material is insufficient, judge only what can be evaluated and
   say so in the feedback.
"""

FINAL_REPORT_SYSTEM_INSTRUCTION = """
You are the senior assessment lead writing the final evaluation report for a
completed technical interview.

Write a concise overall assessment (a few sentences) summarising the candidate's
performance, the strongest parts of the interview performance and the overall
readiness or gaps before a hiring decision.
"""


class EvaluationError(Exception):
    """Raised when an answer cannot be evaluated or a report cannot be produced."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class AnswerEvaluation:
    """Validated evaluation of one answer plus the topic it was scored on."""

    technical_score: float
    relevance_score: float
    depth_score: float
    clarity_score: float
    overall_score: float
    feedback: str
    improvements: list[str] = field(default_factory=list)
    topic: str = ""

    @property
    def criterion_scores(self) -> dict[str, float]:
        """Map criterion names onto their 0-10 scores for serialisation."""
        return {
            "technical_score": self.technical_score,
            "relevance_score": self.relevance_score,
            "depth_score": self.depth_score,
            "clarity_score": self.clarity_score,
        }


@dataclass(frozen=True)
class InterviewReportResult:
    """Aggregated final report content derived from persisted evaluations."""

    overall_score: float
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    recommended_topics: list[str] = field(default_factory=list)
    assessment: str = ""


def _retrieval_context(question, role: JobRole) -> list[RetrievedChunk]:
    """Retrieve the knowledge excerpts that ground an evaluation."""
    chunks = retrieval.search_knowledge(
        query=f"{question.topic} core concepts and fundamentals",
        role=role.slug,
        top_k=MAX_CONTEXT_CHUNKS,
    )
    selected: list[RetrievedChunk] = []
    used_chars = 0
    for chunk in chunks:
        if len(selected) >= MAX_CONTEXT_CHUNKS:
            break
        if selected and used_chars + len(chunk.text) > MAX_CONTEXT_CHARS:
            break
        selected.append(chunk)
        used_chars += len(chunk.text)
    return selected


def _format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for index, chunk in enumerate(chunks, start=1):
        blocks.append(
            f"[{index}] document: {chunk.source} | section: {chunk.section or 'untitled'}\n{chunk.text}"
        )
    return "\n\n".join(blocks)


def _evaluation_prompt(
    profile: CandidateProfile,
    question,
    answer: str,
    chunks: list[RetrievedChunk],
) -> str:
    lines: list[str] = [
        f"Question: {question.text}",
        f"Question type: {question.question_type}",
        f"Difficulty: {question.difficulty}",
        f"Topic: {question.topic}",
        "",
        "Candidate answer:",
        answer,
        "",
        "Knowledge base excerpts (the reference material):",
        _format_context(chunks),
    ]
    return "\n".join(lines)


def _build_evaluation(
    payload: AnswerEvaluationResult,
    question,
) -> AnswerEvaluation:
    overall = round(
        (
            payload.technical_score
            + payload.relevance_score
            + payload.depth_score
            + payload.clarity_score
        )
        / 4,
        2,
    )
    return AnswerEvaluation(
        technical_score=payload.technical_score,
        relevance_score=payload.relevance_score,
        depth_score=payload.depth_score,
        clarity_score=payload.clarity_score,
        overall_score=overall,
        feedback=payload.feedback,
        improvements=list(payload.improvements),
        topic=question.topic or "",
    )


def evaluate_answer(
    profile: CandidateProfile,
    role: JobRole,
    question,
    answer: str,
) -> AnswerEvaluation:
    """
    Evaluate one candidate answer against the role's knowledge base.

    Raises ``EvaluationError`` when the answer cannot be grounded or the AI
    service fails, mirroring the question-generation error handling.
    """
    answer = (answer or "").strip()
    if not answer:
        raise EvaluationError("Cannot evaluate an empty answer.", status_code=400)

    chunks = _retrieval_context(question, role)
    if not chunks:
        raise EvaluationError(
            f"No knowledge base content is available for role '{role.slug}'.",
            status_code=503,
        )

    settings = get_settings()
    api_key = settings.effective_gemini_api_key
    if not api_key:
        raise EvaluationError(
            "AI service configuration missing: GEMINI_API_KEY is not set. "
            "Please configure GEMINI_API_KEY in backend/.env.",
            status_code=503,
        )

    prompt = _evaluation_prompt(profile, question, answer, chunks)

    try:
        client = genai.Client(api_key=api_key)
        model, raw_text = generate_json_with_fallback(
            client,
            settings.gemini_model_candidates,
            contents=prompt,
            system_instruction=EVALUATION_SYSTEM_INSTRUCTION,
            response_schema=AnswerEvaluationResult,
            temperature=0.4,
            empty_response_message="Gemini returned an empty response during answer evaluation.",
        )
    except AIResponseError as exc:
        raise EvaluationError(exc.message, status_code=exc.status_code) from exc
    except APIError as exc:
        raise EvaluationError(
            f"Gemini API error during answer evaluation: {exc.message}", status_code=502
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during answer evaluation: %s", exc)
        raise EvaluationError(
            "An unexpected error occurred while evaluating the answer.", status_code=500
        ) from exc

    try:
        payload = AnswerEvaluationResult.model_validate(json.loads(strip_json_fences(raw_text)))
    except json.JSONDecodeError as exc:
        logger.exception("Failed to parse evaluation JSON: %s", exc)
        raise EvaluationError("Failed to decode the evaluation from the AI response.", status_code=502) from exc
    except ValidationError as exc:
        logger.exception("AI evaluation did not match the expected schema: %s", exc)
        raise EvaluationError("The AI returned an evaluation in an unexpected format.", status_code=502) from exc

    evaluation = _build_evaluation(payload, question)
    logger.info(
        "Evaluated answer for question=%s position=%s scores=(technical=%s, relevance=%s, depth=%s, clarity=%s, overall=%s)",
        question.topic,
        getattr(question, "position", "?"),
        evaluation.technical_score,
        evaluation.relevance_score,
        evaluation.depth_score,
        evaluation.clarity_score,
        evaluation.overall_score,
    )
    return evaluation


def _fallback_assessment(
    candidate_name: str,
    role_title: str,
    overall_score: float,
    answered_count: int,
    question_count: int,
) -> str:
    """Deterministic assessment used when the narrative model call fails."""
    return (
        f"{candidate_name} completed a {question_count}-question interview for the "
        f"{role_title} role. The candidate answered {answered_count} question(s) with an "
        f"overall answer score of {overall_score}/10. Strengths and weaknesses were derived "
        f"from the persisted answer evaluations."
    )


def generate_report(
    candidate_name: str,
    role: JobRole,
    question_count: int,
    evaluations: list[AnswerEvaluation],
) -> InterviewReportResult:
    """
    Build the final interview report from persisted answer evaluations.

    The overall score is the mean of the evaluated answers' overall scores; only
    submitted answers are ever evaluated, so unanswered questions are not
    counted as successful answers.
    """
    if not evaluations:
        raise EvaluationError(
            "Cannot generate an interview report without answer evaluations.",
            status_code=409,
        )

    overall_score = round(
        sum(evaluation.overall_score for evaluation in evaluations) / len(evaluations), 2
    )
    strengths = sorted(
        {
            evaluation.topic
            for evaluation in evaluations
            if evaluation.overall_score >= 7.0
        }
    )
    weaknesses = sorted(
        {
            evaluation.topic
            for evaluation in evaluations
            if evaluation.overall_score < 5.0
        }
    )
    recommended_topics = sorted({evaluation.topic for evaluation in evaluations if evaluation.overall_score < 5.0})

    assessment = _fallback_assessment(
        candidate_name=candidate_name,
        role_title=role.title,
        overall_score=overall_score,
        answered_count=len(evaluations),
        question_count=question_count,
    )
    try:
        settings = get_settings()
        api_key = settings.effective_gemini_api_key
        if api_key:
            client = genai.Client(api_key=api_key)
            result = FinalReportResult.model_validate(
                json.loads(
                    strip_json_fences(
                        generate_json_with_fallback(
                            client,
                            settings.gemini_model_candidates,
                            contents=(
                                "Summarise the final interview assessment.\n\n"
                                f"Candidate: {candidate_name}\nRole: {role.title}\n"
                                f"Overall score: {overall_score}/10\n"
                                f"Answered: {len(evaluations)}/{question_count}\n"
                                + "\n".join(
                                    f"- topic={e.topic} overall={e.overall_score} feedback={e.feedback}"
                                    for e in evaluations
                                )
                            ),
                            system_instruction=FINAL_REPORT_SYSTEM_INSTRUCTION,
                            response_schema=FinalReportResult,
                            temperature=0.3,
                            empty_response_message="Gemini returned an empty response during report generation.",
                        )[1]
                    )
                )
            )
            assessment = result.assessment
    except Exception as exc:
        logger.warning("Final report narrative generation failed; using fallback assessment: %s", exc)

    return InterviewReportResult(
        overall_score=overall_score,
        strengths=strengths,
        weaknesses=weaknesses,
        recommended_topics=recommended_topics,
        assessment=assessment,
    )


__all__ = [
    "AnswerEvaluation",
    "EvaluationError",
    "InterviewReportResult",
    "generate_report",
    "evaluate_answer",
]
