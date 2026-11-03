import hashlib
import re
import uuid
from pathlib import Path

import chromadb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.roles import router as roles_router
from app.core.config import get_settings
from app.core.job_roles import get_role, role_slugs
from app.services.rag import chunking, embeddings, ingestion, retrieval, store

# --- Helpers ---------------------------------------------------------------

SHARED_SENTENCE = "Careful design and measurement matter in every production system."

CORPUS = {
    "ai-ml-engineer/synthetic/optimization.txt": (
        "OPTIMIZATION\n\n"
        "Gradient descent minimizes the loss by following the negative gradient. "
        "The learning rate controls the step size, and momentum smooths noisy updates. "
        "A learning rate that is too large diverges while one that is too small converges slowly.\n\n"
        f"{SHARED_SENTENCE}\n"
    ),
    "backend-engineer/synthetic/apis.txt": (
        "IDEMPOTENCY\n\n"
        "Retrying a request safely requires an idempotency key so duplicate writes cannot occur. "
        "Connection pooling bounds database concurrency and queue depth.\n\n"
        f"{SHARED_SENTENCE}\n"
    ),
    "data-scientist/synthetic/experiments.txt": (
        "EXPERIMENT DESIGN\n\n"
        "A p value measures how surprising the observed data would be under the null hypothesis. "
        "Power analysis determines the sample size needed to detect an effect.\n\n"
        f"{SHARED_SENTENCE}\n"
    ),
}


def _hash_vector(text: str) -> list[float]:
    """Deterministic bag-of-words embedding for hermetic tests."""
    vector = [0.0] * get_settings().embedding_dimensions
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if len(token) < 3:
            continue
        index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % len(vector)
        vector[index] += 1.0
    return vector


class _RecordingEmbedder:
    """Stand-in for Gemini embeddings that records how often it is called."""

    def __init__(self) -> None:
        self.calls = 0
        self.texts_embedded = 0

    def __call__(self, texts, task_type=embeddings.RETRIEVAL_DOCUMENT):
        self.calls += 1
        self.texts_embedded += len(texts)
        return [_hash_vector(text) for text in texts]


@pytest.fixture
def vector_store(monkeypatch):
    """In-memory ChromaDB plus a fake embedder, so tests never call the network."""
    # EphemeralClient instances share one backing store, so each test gets a
    # uniquely named collection instead of relying on a reset between tests.
    monkeypatch.setattr(store, "_client", chromadb.EphemeralClient())
    monkeypatch.setattr(get_settings(), "chroma_collection", f"test_{uuid.uuid4().hex[:12]}")
    embedder = _RecordingEmbedder()
    monkeypatch.setattr(embeddings, "embed_texts", embedder)
    yield embedder


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    for relative, content in CORPUS.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


# --- Chunking --------------------------------------------------------------

def test_chunk_document_tags_sections():
    text = (
        "# Gradient Descent\n\n"
        "Gradient descent follows the negative gradient of the loss.\n\n"
        "## Regularization\n\n"
        "L2 regularization shrinks weights toward zero.\n"
    )
    chunks = chunking.chunk_document(text)

    assert [chunk.section for chunk in chunks] == ["Gradient Descent", "Regularization"]
    assert "negative gradient" in chunks[0].text
    assert "shrinks weights" in chunks[1].text
    assert [chunk.index for chunk in chunks] == [0, 1]


def test_chunk_document_respects_size_limit_and_overlap():
    text = " ".join(
        f"Sentence number {index} describes an aspect of the model behaviour in detail."
        for index in range(80)
    )
    chunks = chunking.chunk_document(text, chunk_size=400, overlap=80)

    assert len(chunks) > 1
    assert max(len(chunk.text) for chunk in chunks) <= 400 + 80

    # Overlap: each chunk restarts with units that already appeared in the previous one.
    first_units = chunks[0].text.split("\n\n")
    second_units = chunks[1].text.split("\n\n")
    assert len(second_units) > 1
    assert second_units[0] in first_units
    assert chunks[1].text.startswith(second_units[0])


def test_chunk_document_splits_text_without_punctuation():
    text = " ".join(f"token{index}" for index in range(500))
    chunks = chunking.chunk_document(text, chunk_size=200, overlap=40)

    assert len(chunks) > 1
    assert max(len(chunk.text) for chunk in chunks) <= 240


def test_chunk_document_returns_nothing_for_blank_text():
    assert chunking.chunk_document("   \n\n  ") == []


def test_chunk_document_rejects_invalid_parameters():
    with pytest.raises(ValueError):
        chunking.chunk_document("some text", chunk_size=0)
    with pytest.raises(ValueError):
        chunking.chunk_document("some text", chunk_size=100, overlap=100)


# --- Role catalog ----------------------------------------------------------

def test_catalog_contains_required_roles():
    assert set(role_slugs()) == {"ai-ml-engineer", "backend-engineer", "data-scientist"}
    role = get_role("ai-ml-engineer")
    assert role is not None
    assert role.title == "AI/ML Engineer"
    assert "Python" in role.key_skills
    assert get_role("unknown-role") is None


def test_roles_endpoint_returns_catalog():
    app = FastAPI()
    app.include_router(roles_router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/roles")

    assert response.status_code == 200
    payload = response.json()
    slugs = [role["slug"] for role in payload["roles"]]
    assert slugs == ["ai-ml-engineer", "backend-engineer", "data-scientist"]
    assert all(role["key_skills"] for role in payload["roles"])


# --- Ingestion -------------------------------------------------------------

def test_chunk_ids_are_deterministic():
    first = store.build_chunk_id("ai-ml-engineer/doc.txt", 0, "some chunk text")
    assert first == store.build_chunk_id("ai-ml-engineer/doc.txt", 0, "some chunk text")
    assert first != store.build_chunk_id("ai-ml-engineer/doc.txt", 1, "some chunk text")
    assert first != store.build_chunk_id("backend-engineer/doc.txt", 0, "some chunk text")


def test_ingestion_marks_synthetic_documents(vector_store, corpus):
    summary = ingestion.ingest_corpus(corpus)

    assert len(summary.ingested_files) == 3
    assert summary.chunks_written == 3

    stored = store.get_collection().get(include=["metadatas"])
    assert {metadata["corpus"] for metadata in stored["metadatas"]} == {"synthetic"}
    assert {metadata["role"] for metadata in stored["metadatas"]} == set(role_slugs())


def test_ingestion_is_idempotent(vector_store, corpus):
    first = ingestion.ingest_corpus(corpus)
    calls_after_first = vector_store.calls
    count_after_first = store.count_chunks()

    second = ingestion.ingest_corpus(corpus)

    assert first.chunks_written == 3
    assert len(second.ingested_files) == 0
    assert len(second.skipped_files) == 3
    assert {report.reason for report in second.skipped_files} == {"unchanged"}
    assert store.count_chunks() == count_after_first
    # Unchanged documents must not be re-embedded.
    assert vector_store.calls == calls_after_first


def test_ingestion_replaces_changed_document_without_duplicates(vector_store, corpus):
    ingestion.ingest_corpus(corpus)
    target = corpus / "ai-ml-engineer/synthetic/optimization.txt"
    source = "ai-ml-engineer/synthetic/optimization.txt"
    before = store.get_collection().get(where={"source": source}, include=["documents"])
    assert any("Gradient descent" in document for document in before["documents"])

    target.write_text(
        "TRANSFORMERS\n\nSelf attention lets every position attend to every other position.\n",
        encoding="utf-8",
    )
    summary = ingestion.ingest_corpus(corpus, role_filters=["ai-ml-engineer"])

    assert summary.ingested_files[0].source == source
    after = store.get_collection().get(where={"source": source}, include=["documents"])
    assert len(after["ids"]) == len(set(after["ids"]))
    assert all("Gradient descent" not in document for document in after["documents"])
    assert any("Self attention" in document for document in after["documents"])


def test_ingestion_skips_unknown_role_directories(vector_store, corpus):
    (corpus / "not-a-role").mkdir()
    (corpus / "not-a-role" / "stray.txt").write_text("stray content", encoding="utf-8")

    summary = ingestion.ingest_corpus(corpus)

    assert len(summary.ingested_files) == 3
    assert not any(report.role == "not-a-role" for report in summary.files)


def test_ingestion_rejects_unknown_role_filter(vector_store, corpus):
    with pytest.raises(ingestion.KnowledgeIngestionError) as exc_info:
        ingestion.ingest_corpus(corpus, role_filters=["not-a-role"])
    assert "Unknown job role" in exc_info.value.message


def test_ingestion_reports_missing_corpus(vector_store, tmp_path):
    with pytest.raises(ingestion.KnowledgeIngestionError):
        ingestion.ingest_corpus(tmp_path / "missing")


# --- Retrieval (smoke test) ------------------------------------------------

def test_retrieval_returns_relevant_chunks_for_role(vector_store, corpus):
    ingestion.ingest_corpus(corpus)

    results = retrieval.search_knowledge(
        "gradient descent learning rate step size", role="ai-ml-engineer", top_k=3
    )

    assert results, "Expected at least one chunk for a query grounded in the corpus"
    assert all(chunk.role == "ai-ml-engineer" for chunk in results)
    assert all(chunk.source.startswith("ai-ml-engineer/") for chunk in results)
    assert "gradient" in results[0].text.lower()
    assert results[0].corpus == "synthetic"
    assert results[0].role_title == "AI/ML Engineer"


def test_retrieval_is_role_filtered_even_for_shared_content(vector_store, corpus):
    ingestion.ingest_corpus(corpus)

    # The shared sentence exists in all three role documents.
    unfiltered = retrieval.search_knowledge(SHARED_SENTENCE, top_k=5)
    assert len({chunk.role for chunk in unfiltered}) > 1

    for role in role_slugs():
        filtered = retrieval.search_knowledge(SHARED_SENTENCE, role=role, top_k=5)
        assert filtered
        assert {chunk.role for chunk in filtered} == {role}
        assert {chunk.source.split("/")[0] for chunk in filtered} == {role}


def test_retrieval_never_returns_another_roles_content(vector_store, corpus):
    ingestion.ingest_corpus(corpus)

    results = retrieval.search_knowledge(
        "idempotency key duplicate writes", role="ai-ml-engineer", top_k=5
    )

    assert all("idempotency" not in chunk.text.lower() for chunk in results)
    assert all(chunk.role == "ai-ml-engineer" for chunk in results)


def test_retrieval_rejects_unknown_role(vector_store, corpus):
    ingestion.ingest_corpus(corpus)
    with pytest.raises(retrieval.UnknownRoleError):
        retrieval.search_knowledge("gradient descent", role="not-a-role")


def test_retrieval_rejects_blank_query(vector_store, corpus):
    ingestion.ingest_corpus(corpus)
    with pytest.raises(ValueError):
        retrieval.search_knowledge("   ", role="ai-ml-engineer")
    with pytest.raises(ValueError):
        retrieval.search_knowledge("gradient", role="ai-ml-engineer", top_k=0)


def test_retrieval_on_empty_collection_returns_nothing(vector_store):
    assert retrieval.search_knowledge("anything at all", role="ai-ml-engineer") == []
