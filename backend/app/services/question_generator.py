"""Grounded, personalised interview question generation.

Questions are generated from role-scoped knowledge base chunks retrieved with
the existing RAG pipeline, and personalised using the stored candidate profile.
Each question records the document and section it was grounded in, so an
unverifiable question is visibly unverifiable rather than silently generic.
"""

import json
import logging
from dataclasses import dataclass, field

from google import genai
from google.genai.errors import APIError
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.job_roles import JobRole
from app.schemas.interview import GeneratedInterview
from app.schemas.resume import CandidateProfile
from app.services.gemini_client import (
    AIResponseError,
    generate_json_with_fallback,
    strip_json_fences,
)
from app.services.rag import retrieval
from app.services.rag.embeddings import EmbeddingError
from app.services.rag.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

#: Maximum excerpts handed to the model in one prompt.
MAX_CONTEXT_CHUNKS = 8

#: Rough character budget for retrieved context, keeping prompts cheap.
MAX_CONTEXT_CHARS = 9000

#: Retrieval queries issued per generation (role fundamentals plus candidate focus).
MAX_QUERIES = 3

#: Candidate skills retained for personalisation.
MAX_FOCUS_SKILLS = 6

INTERVIEW_SYSTEM_INSTRUCTION = """
You are a senior technical interviewer at InterView AI writing questions for a live, spoken interview.

Grounding rules:
1. Every question must be answerable from the numbered knowledge excerpts. Use the concepts, definitions, trade-offs and failure modes that appear there; never introduce a topic the excerpts do not cover.
2. Set source_index to the 1-based number of the excerpt that grounds the question, and prefer the excerpt whose section matches the question's topic.
3. Use the candidate profile only to choose angle, depth and wording. Never invent experience, employers, projects, skills or credentials.

Set composition:
- technical questions ask the candidate to design, debug, compare alternatives or reason about trade-offs using the excerpted material.
- conceptual questions ask why a mechanism works, what it assumes, or when it fails.
- Aim for roughly 60% technical and 40% conceptual, and spread difficulty across easy, medium and hard calibrated to the candidate's seniority. Include at least one hard question when the set has three or more questions.
- Cover different excerpts and topics: each question must be distinct in substance, not merely reworded.
- Ask one focused question per item. Avoid trivia, yes/no prompts and multi-part questions.
- topic is a short 2-4 word label taken from the excerpted material.
- rationale is one sentence explaining why this question suits this specific candidate.
"""


class QuestionGenerationError(Exception):
    """Raised when an interview cannot be generated or grounded."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class QuestionDraft:
    """A validated question plus the knowledge chunk that grounds it."""

    text: str
    question_type: str
    difficulty: str
    topic: str
    rationale: str
    source_document: str
    source_section: str


@dataclass
class QuestionGenerationResult:
    """Questions ready to persist, with the candidate focus used to personalise them."""

    questions: list[QuestionDraft] = field(default_factory=list)
    focus_skills: list[str] = field(default_factory=list)


def candidate_focus_skills(profile: CandidateProfile, role: JobRole) -> list[str]:
    """
    Pick up to ``MAX_FOCUS_SKILLS`` candidate skills, preferring role overlap.

    Skills the candidate lists that also appear in the role catalog come first
    (in catalog order), because those are the most relevant hooks for an
    interview about that role. Anything else the candidate claims follows.
    """
    role_skill_order = {skill.lower(): index for index, skill in enumerate(role.key_skills)}
    overlap: list[str] = []
    others: list[str] = []
    seen: set[str] = set()

    candidates = [
        *profile.programming_languages,
        *profile.frameworks_and_tools,
        *profile.technical_skills,
        *profile.relevant_domains,
    ]
    for raw_skill in candidates:
        skill = (raw_skill or "").strip()
        key = skill.lower()
        if not skill or key in seen:
            continue
        seen.add(key)
        if key in role_skill_order:
            overlap.append(skill)
        else:
            others.append(skill)

    overlap.sort(key=lambda skill: role_skill_order[skill.lower()])
    return (overlap + others)[:MAX_FOCUS_SKILLS]


def _retrieval_queries(role: JobRole, focus_skills: list[str]) -> list[str]:
    """Build focused retrieval queries instead of one diluted keyword soup."""
    queries = [f"{role.title} core concepts and technical fundamentals"]
    for skill in focus_skills[: MAX_QUERIES - 1]:
        queries.append(f"{skill} principles and trade-offs")
    return queries[:MAX_QUERIES]


def _collect_context(
    role: JobRole,
    focus_skills: list[str],
    question_count: int,
) -> list[RetrievedChunk]:
    """
    Retrieve role-scoped excerpts, de-duplicated and ranked by similarity.

    Multiple focused queries are merged because a single embedding can only
    represent one topic, while an interview spans several. The result is capped
    by both chunk count and character budget so the prompt stays predictable.
    """
    per_query = max(3, min(5, question_count))
    collected: dict[tuple[str, int], RetrievedChunk] = {}

    try:
        for query in _retrieval_queries(role, focus_skills):
            for chunk in retrieval.search_knowledge(query, role=role.slug, top_k=per_query):
                collected.setdefault((chunk.source, chunk.chunk_index), chunk)
    except EmbeddingError as exc:
        raise QuestionGenerationError(exc.message, status_code=exc.status_code) from exc

    ordered = sorted(collected.values(), key=lambda chunk: chunk.distance)

    selected: list[RetrievedChunk] = []
    used_chars = 0
    for chunk in ordered:
        if len(selected) >= MAX_CONTEXT_CHUNKS:
            break
        if selected and used_chars + len(chunk.text) > MAX_CONTEXT_CHARS:
            break
        selected.append(chunk)
        used_chars += len(chunk.text)

    return selected


def _format_context(chunks: list[RetrievedChunk]) -> str:
    """Render excerpts with 1-based indices matching ``source_index`` in the schema."""
    blocks = []
    for index, chunk in enumerate(chunks, start=1):
        blocks.append(
            f"[{index}] document: {chunk.source} | section: {chunk.section or 'untitled'} "
            f"| role: {chunk.role_title}\n{chunk.text}"
        )
    return "\n\n".join(blocks)


def _candidate_summary(profile: CandidateProfile) -> str:
    """Condense the stored profile into compact prompt material."""
    lines: list[str] = []
    if profile.name:
        lines.append(f"Name: {profile.name}")

    if profile.work_experience:
        lines.append("Experience:")
        for item in profile.work_experience[:3]:
            details = "; ".join(item.description[:3])[:300]
            line = f"- {item.role} at {item.company} ({item.duration or 'dates not stated'})"
            lines.append(f"{line}: {details}" if details else line)

    if profile.projects:
        lines.append("Projects:")
        for project in profile.projects[:3]:
            technologies = ", ".join(project.technologies)
            description = (project.description or "")[:240]
            line = f"- {project.title}"
            if technologies:
                line += f" [{technologies}]"
            lines.append(f"{line}: {description}" if description else line)

    skill_groups = (
        ("Programming languages", profile.programming_languages),
        ("Frameworks and tools", profile.frameworks_and_tools),
        ("Technical skills", profile.technical_skills),
        ("Domains", profile.relevant_domains),
        ("Certifications", profile.certifications),
    )
    for label, values in skill_groups:
        if values:
            lines.append(f"{label}: {', '.join(values[:12])}")

    if profile.education:
        education = profile.education[0]
        lines.append(
            f"Education: {education.degree or ''} {education.field_of_study or ''} "
            f"at {education.institution}".replace("  ", " ").strip()
        )

    return "\n".join(lines) or "No structured profile details are available."


def _build_prompt(
    profile: CandidateProfile,
    role: JobRole,
    chunks: list[RetrievedChunk],
    question_count: int,
) -> str:
    return (
        f"Design exactly {question_count} interview questions for the {role.title} role "
        f"({role.category}).\n\n"
        f"Role summary: {role.description}\n"
        f"Role focus areas: {', '.join(role.key_skills)}\n\n"
        "Candidate profile:\n"
        f"{_candidate_summary(profile)}\n\n"
        "Knowledge excerpts (the only permitted source material):\n\n"
        f"{_format_context(chunks)}"
    )


def _log_composition(questions: list[QuestionDraft]) -> None:
    """Record the type/difficulty spread and warn when it is not balanced."""
    by_type: dict[str, int] = {}
    by_difficulty: dict[str, int] = {}
    for question in questions:
        by_type[question.question_type] = by_type.get(question.question_type, 0) + 1
        by_difficulty[question.difficulty] = by_difficulty.get(question.difficulty, 0) + 1

    logger.info(
        "Question composition: %d question(s), types=%s, difficulty=%s",
        len(questions),
        by_type,
        by_difficulty,
    )
    if len(questions) >= 2 and len(by_type) < 2:
        logger.warning("Generated set lacks a technical/conceptual mix: %s", by_type)
    if len(questions) >= 2 and len(by_difficulty) < 2:
        logger.warning("Generated set uses a single difficulty level: %s", by_difficulty)


def _to_drafts(payload: GeneratedInterview, chunks: list[RetrievedChunk]) -> list[QuestionDraft]:
    """
    Keep only distinct questions whose cited excerpt exists.

    An out-of-range ``source_index`` means the question is not actually grounded
    in the retrieved material, so it is dropped rather than stored as if it were.
    """
    drafts: list[QuestionDraft] = []
    seen_texts: set[str] = set()

    for generated in payload.questions:
        normalised = " ".join(generated.text.lower().split())
        if normalised in seen_texts:
            logger.warning("Dropped duplicate question: %s", generated.text[:80])
            continue
        if not 1 <= generated.source_index <= len(chunks):
            logger.warning(
                "Dropped ungrounded question (source_index=%s of %d): %s",
                generated.source_index,
                len(chunks),
                generated.text[:80],
            )
            continue

        chunk = chunks[generated.source_index - 1]
        seen_texts.add(normalised)
        drafts.append(
            QuestionDraft(
                text=generated.text,
                question_type=generated.question_type,
                difficulty=generated.difficulty,
                topic=generated.topic,
                rationale=generated.rationale,
                source_document=chunk.source,
                source_section=chunk.section,
            )
        )

    return drafts


def generate_interview_questions(
    profile: CandidateProfile,
    role: JobRole,
    question_count: int,
) -> QuestionGenerationResult:
    """
    Generate grounded interview questions for a candidate and role.

    Raises ``QuestionGenerationError`` when the role has no indexed knowledge,
    the API key is missing, Gemini fails, or no usable grounded questions come
    back, so callers never persist a session with invented content.
    """
    if question_count <= 0:
        raise QuestionGenerationError(
            "question_count must be greater than zero.", status_code=400
        )

    focus_skills = candidate_focus_skills(profile, role)
    chunks = _collect_context(role, focus_skills, question_count)
    if not chunks:
        raise QuestionGenerationError(
            f"No knowledge base content is available for role '{role.slug}'. "
            f"Index it with: python -m app.scripts.ingest_knowledge --role {role.slug}",
            status_code=503,
        )

    settings = get_settings()
    api_key = settings.effective_gemini_api_key
    if not api_key:
        logger.error("GEMINI_API_KEY is not configured; cannot generate interview questions.")
        raise QuestionGenerationError(
            "AI service configuration missing: GEMINI_API_KEY is not set. "
            "Please configure GEMINI_API_KEY in backend/.env.",
            status_code=503,
        )

    prompt = _build_prompt(profile, role, chunks, question_count)

    try:
        client = genai.Client(api_key=api_key)
        model, raw_text = generate_json_with_fallback(
            client,
            settings.gemini_model_candidates,
            contents=prompt,
            system_instruction=INTERVIEW_SYSTEM_INSTRUCTION,
            response_schema=GeneratedInterview,
            temperature=0.6,
            empty_response_message="Gemini returned an empty response during question generation.",
        )
    except AIResponseError as exc:
        logger.error("AI question generation failed: %s", exc.message)
        raise QuestionGenerationError(exc.message, status_code=exc.status_code) from exc
    except APIError as exc:
        logger.exception("Gemini API error during question generation: %s", exc)
        raise QuestionGenerationError(
            f"Gemini API error during question generation: {exc.message}",
            status_code=502,
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during question generation: %s", exc)
        raise QuestionGenerationError(
            f"An unexpected error occurred while generating interview questions: {exc}",
            status_code=500,
        ) from exc

    try:
        payload = GeneratedInterview.model_validate(json.loads(strip_json_fences(raw_text)))
    except json.JSONDecodeError as exc:
        logger.exception("Failed to parse Gemini question JSON: %s", exc)
        raise QuestionGenerationError(
            "Failed to decode generated questions from the AI response.", status_code=502
        ) from exc
    except ValidationError as exc:
        logger.exception("Gemini questions did not match the expected schema: %s", exc)
        raise QuestionGenerationError(
            "The AI returned questions in an unexpected format.", status_code=502
        ) from exc

    drafts = _to_drafts(payload, chunks)
    if not drafts:
        raise QuestionGenerationError(
            "Gemini returned no usable grounded questions. Please retry.", status_code=502
        )
    if len(drafts) > question_count:
        drafts = drafts[:question_count]
    if len(drafts) < question_count:
        logger.warning(
            "Requested %d question(s) but only %d grounded question(s) were usable.",
            question_count,
            len(drafts),
        )

    _log_composition(drafts)
    logger.info(
        "Generated %d grounded question(s) for role=%s using model '%s' from %d excerpt(s)",
        len(drafts),
        role.slug,
        model,
        len(chunks),
    )
    return QuestionGenerationResult(questions=drafts, focus_skills=focus_skills)
