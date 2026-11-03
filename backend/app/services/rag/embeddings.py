"""Gemini embedding generation for the knowledge base.

Embeddings are produced explicitly and handed to ChromaDB, so no local
embedding model (or ONNX runtime) is ever downloaded. Documents are embedded
with RETRIEVAL_DOCUMENT and queries with RETRIEVAL_QUERY, which is the pairing
the Gemini embedding models are trained for.
"""

import logging
from collections.abc import Sequence

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: Texts per embed_content request. Small enough to stay well inside provider limits.
EMBED_BATCH_SIZE = 32

RETRIEVAL_DOCUMENT = "RETRIEVAL_DOCUMENT"
RETRIEVAL_QUERY = "RETRIEVAL_QUERY"


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def embed_texts(
    texts: Sequence[str],
    task_type: str = RETRIEVAL_DOCUMENT,
) -> list[list[float]]:
    """Embed texts, preserving input order. Returns one vector per input text."""
    items = [text.strip() for text in texts]
    if not items:
        return []

    for position, item in enumerate(items):
        if not item:
            raise EmbeddingError(f"Cannot embed blank text (position {position}).")

    settings = get_settings()
    api_key = settings.effective_gemini_api_key
    if not api_key:
        logger.error("GEMINI_API_KEY is not configured; cannot generate embeddings.")
        raise EmbeddingError(
            "AI service configuration missing: GEMINI_API_KEY is not set. "
            "Please configure GEMINI_API_KEY in backend/.env.",
            status_code=503,
        )

    client = genai.Client(api_key=api_key)
    config = types.EmbedContentConfig(
        task_type=task_type,
        output_dimensionality=settings.embedding_dimensions,
    )

    vectors: list[list[float]] = []
    for start in range(0, len(items), EMBED_BATCH_SIZE):
        batch = items[start : start + EMBED_BATCH_SIZE]
        try:
            response = client.models.embed_content(
                model=settings.embedding_model,
                contents=batch,
                config=config,
            )
        except APIError as exc:
            logger.exception("Gemini embedding request failed: %s", exc)
            raise EmbeddingError(f"Gemini embedding request failed: {exc.message}") from exc
        except Exception as exc:
            logger.exception("Unexpected error during embedding generation: %s", exc)
            raise EmbeddingError(
                f"An unexpected error occurred while generating embeddings: {exc}"
            ) from exc

        embeddings = list(response.embeddings or [])
        if len(embeddings) != len(batch):
            raise EmbeddingError(
                f"Expected {len(batch)} embeddings but received {len(embeddings)} from "
                f"'{settings.embedding_model}'."
            )

        for embedding in embeddings:
            values = list(embedding.values or [])
            if len(values) != settings.embedding_dimensions:
                raise EmbeddingError(
                    f"Embedding dimension mismatch: model '{settings.embedding_model}' returned "
                    f"{len(values)} dimensions but EMBEDDING_DIMENSIONS is set to "
                    f"{settings.embedding_dimensions}. Re-ingest the knowledge base after "
                    "changing this setting."
                )
            vectors.append(values)

    logger.debug(
        "Embedded %d text(s) with '%s' (%s)", len(vectors), settings.embedding_model, task_type
    )
    return vectors
