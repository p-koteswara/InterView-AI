import json
import logging
import re
from typing import Optional

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.core.config import get_settings
from app.schemas.resume import CandidateProfile

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_INSTRUCTION = """
You are an expert technical talent assessment engine for InterView AI.
Your objective is to extract structured, highly accurate candidate profile data from raw resume text.

Rules:
1. Strict factual grounding: Extract ONLY information explicitly stated in the resume. Do NOT fabricate, infer, or hallucinate credentials, dates, skills, or job roles.
2. If any attribute (such as phone, location, grade) is not present, return null.
3. If entire sections (such as certifications, projects, or work experience) are absent, return empty lists [].
4. Parse technologies cleanly into categorized buckets:
   - programming_languages: Only actual languages (e.g., Python, C++, TypeScript, SQL, Rust).
   - frameworks_and_tools: Libraries, frameworks, databases, and developer tools (e.g., React, FastAPI, Docker, PostgreSQL, PyTorch).
   - technical_skills: Higher-level competencies (e.g., Distributed Systems, REST APIs, CI/CD, Microservices).
   - relevant_domains: Industry / specialized domains evident in their work (e.g., Machine Learning, Backend Engineering, Cloud Infrastructure, Data Engineering).
5. For experience and projects, maintain concise descriptions capturing their responsibilities, impact, and technology stack.
"""


class ProfileExtractionError(Exception):
    """Raised when LLM profile extraction encounters an unrecoverable failure."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _clean_json_output(raw_text: str) -> str:
    """Strip markdown code fence blocks if present."""
    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


#: Provider status codes that indicate a transient problem (rate limiting or
#: capacity) where retrying against a different model may still succeed.
RETRYABLE_STATUS_CODES = frozenset({429, 503})


def _is_retryable_api_error(exc: APIError) -> bool:
    """True only for transient provider errors that justify a fallback attempt."""
    code = getattr(exc, "code", None)
    return isinstance(code, int) and code in RETRYABLE_STATUS_CODES


def _request_profile(client: genai.Client, model: str, prompt: str) -> CandidateProfile:
    """Run one structured-extraction request against a single model."""
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=EXTRACTION_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=CandidateProfile,
            temperature=0.1,
        ),
    )

    if not response or not response.text:
        raise ProfileExtractionError("Gemini returned an empty response during profile extraction.")

    return CandidateProfile.model_validate(json.loads(_clean_json_output(response.text)))


def _extract_with_fallback(
    client: genai.Client,
    models: list[str],
    prompt: str,
) -> CandidateProfile:
    """
    Try each configured model in order.

    Falls back only on transient availability errors; any other failure
    propagates immediately so genuine errors are never masked.
    """
    for index, model in enumerate(models):
        try:
            profile = _request_profile(client, model, prompt)
        except APIError as exc:
            if not _is_retryable_api_error(exc):
                raise

            fallback_model = models[index + 1] if index + 1 < len(models) else None
            if fallback_model is None:
                logger.error(
                    "Gemini model '%s' is temporarily unavailable (%s) and no fallback remains.",
                    model,
                    exc.code,
                )
                raise

            logger.warning(
                "Gemini model '%s' is temporarily unavailable (%s); retrying with fallback '%s'.",
                model,
                exc.code,
                fallback_model,
            )
            continue

        logger.info("Extracted candidate profile using model '%s'.", model)
        return profile

    raise ProfileExtractionError(
        "AI service configuration missing: no Gemini model is configured.",
        status_code=503,
    )


def extract_candidate_profile(resume_text: str) -> CandidateProfile:
    """
    Extract a structured CandidateProfile from raw resume text.

    Uses the configured primary Gemini model, falling back to the configured
    fallback model when the primary reports a temporary availability error.
    """
    settings = get_settings()

    api_key = settings.effective_gemini_api_key
    if not api_key:
        logger.error("GEMINI_API_KEY is not configured in backend settings.")
        raise ProfileExtractionError(
            "AI service configuration missing: GEMINI_API_KEY is not set. "
            "Please configure GEMINI_API_KEY in backend/.env.",
            status_code=503,
        )

    prompt = (
        "Extract the candidate's structured profile from the following resume text:\n\n"
        "--- START OF RESUME TEXT ---\n"
        f"{resume_text}\n"
        "--- END OF RESUME TEXT ---"
    )

    try:
        client = genai.Client(api_key=api_key)
        profile = _extract_with_fallback(client, settings.gemini_model_candidates, prompt)
        logger.info("Successfully extracted candidate profile for: %s", profile.name or "Unknown")
        return profile

    except ProfileExtractionError:
        raise
    except APIError as exc:
        logger.exception("Gemini API error during resume extraction: %s", exc)
        raise ProfileExtractionError(
            f"Gemini API error during candidate profile extraction: {exc.message}",
            status_code=502,
        ) from exc
    except json.JSONDecodeError as exc:
        logger.exception("Failed to parse Gemini JSON output: %s", exc)
        raise ProfileExtractionError(
            "Failed to decode structured profile from AI response.",
            status_code=502,
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during profile extraction: %s", exc)
        raise ProfileExtractionError(
            f"An unexpected error occurred while analyzing candidate profile: {str(exc)}",
            status_code=500,
        ) from exc
