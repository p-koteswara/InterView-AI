"""Shared Gemini structured-generation helper.

Profile extraction and interview question generation both need the same
resilience rules: try the configured primary model, fall back only when the
provider reports a transient availability problem, and never mask a permanent
failure by silently retrying against a different model.
"""

import logging
import re

from google import genai
from google.genai import types
from google.genai.errors import APIError

logger = logging.getLogger(__name__)

#: Provider status codes that indicate a transient problem (rate limiting or
#: capacity) where retrying against a different model may still succeed.
RETRYABLE_STATUS_CODES = frozenset({429, 503})


_FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")


class AIResponseError(Exception):
    """Raised when a Gemini request cannot produce usable structured output."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def strip_json_fences(raw_text: str) -> str:
    """Strip markdown code fences when a model wraps its JSON in them anyway."""
    text = raw_text.strip()
    match = _FENCE_PATTERN.search(text)
    return match.group(1).strip() if match else text


def is_retryable_api_error(exc: APIError) -> bool:
    """True only for transient provider errors that justify a fallback attempt."""
    code = getattr(exc, "code", None)
    return isinstance(code, int) and code in RETRYABLE_STATUS_CODES


def _request_json(
    client: genai.Client,
    model: str,
    contents: str,
    system_instruction: str,
    response_schema: type,
    temperature: float,
    empty_response_message: str,
) -> str:
    """Run one structured JSON request against a single model."""
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=temperature,
        ),
    )

    if not response or not response.text:
        raise AIResponseError(empty_response_message)

    return response.text


def generate_json_with_fallback(
    client: genai.Client,
    models: list[str],
    *,
    contents: str,
    system_instruction: str,
    response_schema: type,
    temperature: float,
    empty_response_message: str,
) -> tuple[str, str]:
    """
    Generate a structured JSON response, returning ``(model, raw_text)``.

    Each model is tried in order. Falling back happens only on transient
    availability errors; any other failure propagates unchanged so genuine
    errors are never hidden behind a fallback attempt.
    """
    if not models:
        raise AIResponseError(
            "AI service configuration missing: no Gemini model is configured.",
            status_code=503,
        )

    for index, model in enumerate(models):
        try:
            text = _request_json(
                client,
                model,
                contents,
                system_instruction,
                response_schema,
                temperature,
                empty_response_message,
            )
        except APIError as exc:
            if not is_retryable_api_error(exc):
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

        return model, text

    raise AIResponseError(
        "AI service configuration missing: no Gemini model is configured.",
        status_code=503,
    )
