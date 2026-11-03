from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GEMINI_FALLBACK_MODEL = "gemini-3-flash-preview"
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSIONS = 768


class Settings(BaseSettings):
    """Runtime application settings loaded from environment and .env."""

    app_name: str = "InterView AI"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./interview_ai.db"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    gemini_api_key: str = ""
    gemini_model: str = DEFAULT_GEMINI_MODEL
    gemini_fallback_model: str = DEFAULT_GEMINI_FALLBACK_MODEL

    # Retrieval-augmented generation (ChromaDB vector store)
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS
    chroma_db_path: str = "./chroma_db"
    chroma_collection: str = "knowledge_chunks"
    knowledge_base_dir: str = "../knowledge_base"

    @property
    def effective_gemini_api_key(self) -> str:
        import os
        return (
            self.gemini_api_key.strip()
            or os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("GOOGLE_API_KEY", "").strip()
        )

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def gemini_model_candidates(self) -> list[str]:
        """Ordered, de-duplicated Gemini models to try: primary then fallback."""
        names = [
            (self.gemini_model or "").strip() or DEFAULT_GEMINI_MODEL,
            (self.gemini_fallback_model or "").strip() or DEFAULT_GEMINI_FALLBACK_MODEL,
        ]
        candidates: list[str] = []
        for name in names:
            if name not in candidates:
                candidates.append(name)
        return candidates

    @property
    def resolved_chroma_path(self) -> Path:
        """Absolute path of the persistent ChromaDB directory."""
        path = Path(self.chroma_db_path)
        if not path.is_absolute():
            path = (BACKEND_ROOT / path).resolve()
        return path

    @property
    def resolved_knowledge_base_path(self) -> Path:
        """Absolute path of the role-partitioned knowledge base corpus."""
        path = Path(self.knowledge_base_dir)
        if not path.is_absolute():
            path = (BACKEND_ROOT / path).resolve()
        return path

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_database_url(self) -> str:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return self.database_url

        raw_path = self.database_url.removeprefix(prefix)
        path = Path(raw_path)
        if not path.is_absolute():
            path = (BACKEND_ROOT / path).resolve()
        return f"{prefix}{path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()

