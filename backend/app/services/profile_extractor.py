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


def extract_candidate_profile(resume_text: str) -> CandidateProfile:
    """
    Extract a structured CandidateProfile from raw resume text using Gemini 3.8 Flash.
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

    try:
        client = genai.Client(api_key=api_key)

        prompt = (
            "Extract the candidate's structured profile from the following resume text:\n\n"
            "--- START OF RESUME TEXT ---\n"
            f"{resume_text}\n"
            "--- END OF RESUME TEXT ---"
        )

        response = client.models.generate_content(
            model="gemini-3.8-flash",
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

        cleaned = _clean_json_output(response.text)
        data = json.loads(cleaned)
        profile = CandidateProfile.model_validate(data)
        logger.info("Successfully extracted candidate profile for: %s", profile.name or "Unknown")
        return profile

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
        if isinstance(exc, ProfileExtractionError):
            raise
        logger.exception("Unexpected error during profile extraction: %s", exc)
        raise ProfileExtractionError(
            f"An unexpected error occurred while analyzing candidate profile: {str(exc)}",
            status_code=500,
        ) from exc
