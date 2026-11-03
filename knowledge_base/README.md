# Knowledge Base Repository

This directory contains role-specific authoritative reference materials and technical literature used by the Retrieval-Augmented Generation (RAG) pipeline in InterView AI.

The RAG engine queries verified textbook and corpus documents—rather than generic ungrounded internet queries—to anchor technical question generation and candidate evaluation.

### Track Curricula & Reference Corpus

- **AI & Machine Learning Track**:
  - *Machine Learning* (Tom Mitchell)
  - *The Hundred-Page Machine Learning Book* (Andriy Burkov)
  - *Machine Learning for Absolute Beginners*
- **Data Science & Applied ML Track**:
  - *Introduction to Machine Learning with Python*
  - *Master Machine Learning Algorithms* (Jason Brownlee)
- **Advanced & Theoretical ML Track**:
  - *Pattern Recognition and Machine Learning* (Christopher Bishop)
  - *Artificial Intelligence, Machine Learning & Deep Learning*

> Place local reference PDFs or document corpora in this directory for ingestion into the ChromaDB vector database during the RAG indexing workflow.

## Corpus layout

Documents are partitioned by job-role slug, because retrieval is always scoped to a single role:

```
knowledge_base/
├── ai-ml-engineer/
│   ├── <reference-document>.pdf     # real curriculum material
│   └── synthetic/<name>.txt         # generated placeholder test data
├── backend-engineer/
│   └── synthetic/<name>.txt
└── data-scientist/
    └── synthetic/<name>.txt
```

Rules enforced by the ingestion pipeline:

- **Directory names must match a catalog slug** in `backend/app/core/job_roles.py` (`ai-ml-engineer`, `backend-engineer`, `data-scientist`). Any other directory is ignored with a warning, so a typo cannot silently produce an unreachable corpus.
- **Only `.pdf` and `.txt` files are ingested.** `README.md` and `.gitkeep` files are always skipped.
- **Synthetic data lives in a `synthetic/` subdirectory** and is stored with chunk metadata `corpus: "synthetic"`. Everything else is tagged `corpus: "reference"`.

### Synthetic vs. reference material

Everything currently under a `synthetic/` directory is **generated placeholder text written to validate the ingestion and retrieval pipeline**. It is not an excerpt from any published book, it is not authoritative, and it must not be shown to candidates as study material or used to ground interview questions. Replace it with real curriculum PDFs before the RAG workflow feeds anything user-facing.

## Ingestion

Run from the `backend` directory:

```bash
# Ingest every role
python -m app.scripts.ingest_knowledge

# Ingest a single role
python -m app.scripts.ingest_knowledge --role ai-ml-engineer

# Re-embed everything, even unchanged documents
python -m app.scripts.ingest_knowledge --force
```

Vectors are written to `backend/chroma_db/` (git-ignored), collection `knowledge_chunks`. Ingestion is safe to rerun: an unchanged document is skipped without re-embedding, and a changed document has its previous chunks removed before the new ones are written.

Embeddings use `gemini-embedding-001` at `EMBEDDING_DIMENSIONS` (default 768). Vectors from different models or dimensions are not comparable, so changing `EMBEDDING_MODEL` or `EMBEDDING_DIMENSIONS` requires deleting `backend/chroma_db/` and re-ingesting.
