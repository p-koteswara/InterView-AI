"""Offline ingestion of role-scoped knowledge documents into ChromaDB.

Re-running ingestion is safe: a document whose bytes are unchanged is skipped
without re-embedding, and a changed document has all of its previous chunks
removed before the new ones are written, so no duplicates can accumulate.
"""

import hashlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from app.core.job_roles import JobRole, get_role, list_roles, role_slugs
from app.services.rag import embeddings, store
from app.services.rag.chunking import chunk_document
from app.services.resume_parser import (
    ResumeParsingError,
    extract_text_from_pdf,
    extract_text_from_txt,
)

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = frozenset({".pdf", ".txt"})

#: Documents under a `synthetic/` subdirectory are generated test data, not reference material.
SYNTHETIC_DIR_NAME = "synthetic"

#: Conventional repository docs that live beside documents but must never be indexed.
SKIPPED_FILENAMES = frozenset({"readme.md", "readme.txt", ".gitkeep"})


class KnowledgeIngestionError(Exception):
    """Raised when knowledge documents cannot be read or ingested."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class FileReport:
    """Outcome of ingesting one document."""

    source: str
    role: str
    chunks: int = 0
    skipped: bool = False
    reason: str = ""


@dataclass
class IngestionSummary:
    """Aggregate outcome of a corpus ingestion run."""

    files: list[FileReport] = field(default_factory=list)

    @property
    def ingested_files(self) -> list[FileReport]:
        return [report for report in self.files if not report.skipped]

    @property
    def skipped_files(self) -> list[FileReport]:
        return [report for report in self.files if report.skipped]

    @property
    def chunks_written(self) -> int:
        return sum(report.chunks for report in self.files)


def extract_document_text(path: Path, content: bytes) -> str:
    """Extract text from a PDF or TXT knowledge document."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return extract_text_from_pdf(content)
        if suffix == ".txt":
            return extract_text_from_txt(content)
    except ResumeParsingError as exc:
        raise KnowledgeIngestionError(f"Failed to read '{path.name}': {exc.message}") from exc
    raise KnowledgeIngestionError(f"Unsupported knowledge document type '{suffix}'.")


def corpus_label(document_path: Path) -> str:
    """Classify a document as generated test data or reference material."""
    return "synthetic" if SYNTHETIC_DIR_NAME in document_path.parts[:-1] else "reference"


def iter_documents(role_dir: Path) -> Iterable[Path]:
    """Yield ingestable documents below a role directory, in a stable order."""
    for path in sorted(role_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name.lower() in SKIPPED_FILENAMES:
            logger.debug("Skipping documentation file %s", path)
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        yield path


def ingest_document(
    path: Path,
    role: JobRole,
    source: str,
    force: bool = False,
) -> FileReport:
    """Chunk, embed and store a single document."""
    content = path.read_bytes()
    file_hash = hashlib.sha256(content).hexdigest()

    if not force and store.stored_file_hash(source) == file_hash:
        return FileReport(source=source, role=role.slug, skipped=True, reason="unchanged")

    text = extract_document_text(path, content)
    chunks = chunk_document(text)
    if not chunks:
        return FileReport(source=source, role=role.slug, skipped=True, reason="no extractable text")

    vectors = embeddings.embed_texts([chunk.text for chunk in chunks], embeddings.RETRIEVAL_DOCUMENT)

    label = corpus_label(path)
    total = len(chunks)
    ids = [store.build_chunk_id(source, chunk.index, chunk.text) for chunk in chunks]
    metadatas = [
        {
            "source": source,
            "document": path.name,
            "role": role.slug,
            "role_title": role.title,
            "section": chunk.section or "",
            "chunk_index": chunk.index,
            "total_chunks": total,
            "corpus": label,
            "file_hash": file_hash,
        }
        for chunk in chunks
    ]

    store.delete_source(source)
    written = store.upsert_chunks(ids, [chunk.text for chunk in chunks], vectors, metadatas)

    logger.info(
        "Ingested %s (%d chunk(s), role=%s, corpus=%s)", source, written, role.slug, label
    )
    return FileReport(source=source, role=role.slug, chunks=written)


def ingest_corpus(
    base_dir: Path,
    role_filters: Iterable[str] | None = None,
    force: bool = False,
) -> IngestionSummary:
    """Ingest every document under ``base_dir/<role>/`` for the selected roles."""
    base = Path(base_dir)
    if not base.is_dir():
        raise KnowledgeIngestionError(f"Knowledge base directory not found: {base}")

    if role_filters:
        roles: list[JobRole] = []
        for slug in role_filters:
            role = get_role(slug)
            if role is None:
                available = ", ".join(role_slugs())
                raise KnowledgeIngestionError(
                    f"Unknown job role '{slug}'. Available roles: {available}."
                )
            roles.append(role)
    else:
        roles = list_roles()

    known = set(role_slugs())
    for child in sorted(base.iterdir()):
        if child.is_dir() and child.name not in known:
            logger.warning(
                "Ignoring knowledge base directory '%s': not a catalog role slug (%s)",
                child.name,
                ", ".join(sorted(known)),
            )

    summary = IngestionSummary()
    for role in roles:
        role_dir = base / role.slug
        if not role_dir.is_dir():
            logger.warning("No knowledge directory for role '%s' at %s", role.slug, role_dir)
            continue

        for path in iter_documents(role_dir):
            source = path.relative_to(base).as_posix()
            try:
                summary.files.append(ingest_document(path, role, source, force=force))
            except KnowledgeIngestionError as exc:
                logger.error("Skipping '%s': %s", source, exc.message)
                summary.files.append(
                    FileReport(source=source, role=role.slug, skipped=True, reason=exc.message)
                )
            except embeddings.EmbeddingError as exc:
                logger.error("Embedding failed for '%s': %s", source, exc.message)
                summary.files.append(
                    FileReport(source=source, role=role.slug, skipped=True, reason=exc.message)
                )

    return summary
