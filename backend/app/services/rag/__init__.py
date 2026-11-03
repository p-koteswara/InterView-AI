"""Retrieval-augmented generation services (chunking, embeddings, storage, retrieval)."""

from app.services.rag.chunking import DocumentChunk, chunk_document
from app.services.rag.embeddings import EmbeddingError, embed_texts
from app.services.rag.ingestion import (
    IngestionSummary,
    KnowledgeIngestionError,
    ingest_corpus,
)
from app.services.rag.retrieval import (
    RetrievedChunk,
    UnknownRoleError,
    search_knowledge,
)

__all__ = [
    "DocumentChunk",
    "chunk_document",
    "EmbeddingError",
    "embed_texts",
    "IngestionSummary",
    "KnowledgeIngestionError",
    "ingest_corpus",
    "RetrievedChunk",
    "UnknownRoleError",
    "search_knowledge",
]
