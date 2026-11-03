"""Persistent ChromaDB storage for knowledge chunks.

Embeddings are always supplied by :mod:`app.services.rag.embeddings`, so the
collection is created with ``embedding_function=None`` to avoid ChromaDB
downloading a local ONNX embedding model.
"""

import hashlib
import logging
from collections.abc import Sequence
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: Cached ChromaDB client. Tests replace this with an EphemeralClient.
_client: Any | None = None


def get_client() -> Any:
    """Return the process-wide persistent ChromaDB client."""
    global _client
    if _client is None:
        path = get_settings().resolved_chroma_path
        path.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info("Opened persistent ChromaDB store at %s", path)
    return _client


def get_collection() -> Any:
    """Return the knowledge collection, creating it with cosine distance if needed."""
    settings = get_settings()
    return get_client().get_or_create_collection(
        name=settings.chroma_collection,
        configuration={"hnsw": {"space": "cosine"}},
        embedding_function=None,
    )


def build_chunk_id(source: str, index: int, text: str) -> str:
    """Deterministic chunk identifier so re-ingestion can never duplicate a chunk."""
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return hashlib.sha256(f"{source}|{index}|{text_hash}".encode("utf-8")).hexdigest()


def count_chunks() -> int:
    return get_collection().count()


def stored_file_hash(source: str) -> str | None:
    """Return the recorded file hash for a source, or None if absent or inconsistent."""
    existing = get_collection().get(where={"source": source}, include=["metadatas"])
    hashes = {
        metadata.get("file_hash")
        for metadata in (existing.get("metadatas") or [])
        if metadata and metadata.get("file_hash")
    }
    if len(hashes) == 1:
        return hashes.pop()
    return None


def delete_source(source: str) -> int:
    """Remove every chunk belonging to a source document. Returns the prior count."""
    collection = get_collection()
    existing = collection.get(where={"source": source}, include=[])
    removed = len(existing.get("ids") or [])
    if removed:
        collection.delete(where={"source": source})
        logger.debug("Deleted %d stale chunk(s) for %s", removed, source)
    return removed


def upsert_chunks(
    ids: Sequence[str],
    texts: Sequence[str],
    embeddings: Sequence[Sequence[float]],
    metadatas: Sequence[dict[str, Any]],
) -> int:
    """Insert or replace chunks. All arguments must be the same length."""
    if not ids:
        return 0
    if not (len(ids) == len(texts) == len(embeddings) == len(metadatas)):
        raise ValueError("ids, texts, embeddings and metadatas must have equal length.")

    get_collection().upsert(
        ids=list(ids),
        documents=list(texts),
        embeddings=[list(vector) for vector in embeddings],
        metadatas=list(metadatas),
    )
    return len(ids)


def query_chunks(
    embedding: Sequence[float],
    role: str | None = None,
    top_k: int = 5,
) -> dict[str, list[Any]]:
    """Nearest-neighbour search, optionally restricted to a single role."""
    empty: dict[str, list[Any]] = {"ids": [], "documents": [], "metadatas": [], "distances": []}

    collection = get_collection()
    total = collection.count()
    if total == 0:
        logger.warning("Knowledge collection is empty; returning no chunks.")
        return empty

    raw = collection.query(
        query_embeddings=[list(embedding)],
        n_results=min(top_k, total),
        where={"role": role} if role else None,
        include=["documents", "metadatas", "distances"],
    )

    def first(key: str) -> list[Any]:
        # Chroma returns one result list per query embedding.
        values = raw.get(key) or []
        return list(values[0]) if values else []

    return {
        "ids": first("ids"),
        "documents": first("documents"),
        "metadatas": first("metadatas"),
        "distances": first("distances"),
    }
