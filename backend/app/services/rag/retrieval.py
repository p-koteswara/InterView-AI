"""Role-scoped semantic retrieval over the knowledge base."""

import logging
from dataclasses import dataclass
from typing import Any

from app.core.job_roles import get_role, role_slugs
from app.services.rag import embeddings, store

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5


class UnknownRoleError(ValueError):
    """Raised when retrieval is requested for a role outside the catalog."""

    def __init__(self, slug: str):
        available = ", ".join(role_slugs())
        super().__init__(f"Unknown job role '{slug}'. Available roles: {available}.")
        self.slug = slug


@dataclass(frozen=True)
class RetrievedChunk:
    """A knowledge chunk returned by a role-filtered search."""

    text: str
    source: str
    section: str
    role: str
    role_title: str
    corpus: str
    chunk_index: int
    distance: float


def search_knowledge(
    query: str,
    role: str | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> list[RetrievedChunk]:
    """
    Return the chunks most similar to ``query``.

    When ``role`` is given the search is restricted to that role's documents, so
    a query for one hiring track never surfaces another track's material.
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("Query text must not be empty.")
    if top_k <= 0:
        raise ValueError("top_k must be greater than zero.")
    if role is not None and get_role(role) is None:
        raise UnknownRoleError(role)

    query_vector = embeddings.embed_texts([query], task_type=embeddings.RETRIEVAL_QUERY)[0]
    raw: dict[str, list[Any]] = store.query_chunks(query_vector, role=role, top_k=top_k)

    results: list[RetrievedChunk] = []
    for metadata, document, distance in zip(
        raw["metadatas"], raw["documents"], raw["distances"]
    ):
        metadata = metadata or {}
        results.append(
            RetrievedChunk(
                text=document or "",
                source=str(metadata.get("source", "")),
                section=str(metadata.get("section", "")),
                role=str(metadata.get("role", "")),
                role_title=str(metadata.get("role_title", "")),
                corpus=str(metadata.get("corpus", "")),
                chunk_index=int(metadata.get("chunk_index", 0)),
                distance=float(distance),
            )
        )

    logger.info(
        "Retrieved %d chunk(s) for role=%s query=%r", len(results), role or "any", query[:80]
    )
    return results
