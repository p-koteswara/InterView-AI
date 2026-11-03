"""Offline ingestion of the role-partitioned knowledge base into ChromaDB.

Usage (from the ``backend`` directory):

    python -m app.scripts.ingest_knowledge
    python -m app.scripts.ingest_knowledge --role ai-ml-engineer
    python -m app.scripts.ingest_knowledge --force

Safe to rerun: unchanged documents are skipped without re-embedding, and
changed documents replace their previous chunks.
"""

import argparse
import logging
import sys

from app.core.config import get_settings
from app.core.job_roles import role_slugs
from app.core.logging import setup_logging
from app.services.rag import store
from app.services.rag.embeddings import EmbeddingError
from app.services.rag.ingestion import IngestionSummary, KnowledgeIngestionError, ingest_corpus

logger = logging.getLogger("ingest_knowledge")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.ingest_knowledge",
        description="Ingest knowledge base documents into the ChromaDB vector store.",
    )
    parser.add_argument(
        "--role",
        action="append",
        choices=role_slugs(),
        metavar="SLUG",
        help=f"Only ingest one role (repeatable). Choices: {', '.join(role_slugs())}",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed and rewrite documents even when their content is unchanged.",
    )
    return parser


def print_summary(summary: IngestionSummary, corpus_path: str) -> None:
    ingested = summary.ingested_files
    skipped = summary.skipped_files

    print()
    print("Knowledge base ingestion")
    print(f"  corpus      : {corpus_path}")
    print(f"  files       : {len(ingested)} ingested, {len(skipped)} skipped")
    print(f"  chunks      : {summary.chunks_written} written")
    print(f"  collection  : {store.count_chunks()} chunks stored in total")

    if summary.files:
        print()
        width = max(len(report.source) for report in summary.files)
        for report in summary.files:
            status = f"skipped ({report.reason})" if report.skipped else f"{report.chunks} chunk(s)"
            print(f"    {report.source:<{width}}  {report.role:<18}  {status}")
    print()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging()

    corpus_path = get_settings().resolved_knowledge_base_path
    logger.info("Ingesting knowledge base from %s", corpus_path)

    try:
        summary = ingest_corpus(corpus_path, role_filters=args.role, force=args.force)
    except (KnowledgeIngestionError, EmbeddingError) as exc:
        logger.error("Ingestion aborted: %s", exc.message)
        return 1

    print_summary(summary, corpus_path)

    if not summary.files:
        logger.warning(
            "No knowledge documents found. Add PDF or TXT files under "
            "knowledge_base/<role>/ and rerun."
        )
        return 1

    if any(report.skipped and report.reason not in {"unchanged"} for report in summary.files):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
