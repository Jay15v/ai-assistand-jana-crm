"""Environment-driven configuration for the vector DB layer."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "app" / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    log_level: str = "INFO"

    # Source documents (crawled bilingual CRM UI knowledge).
    vector_docs_path: str = str(DATA_DIR / "vector_docs" / "ability_crm_vector_docs.json")

    # ChromaDB, persisted on disk inside app/data.
    chroma_path: str = str(DATA_DIR / "chroma")
    chroma_collection: str = "crm_knowledge"

    # Local multilingual embedding model (fastembed / ONNX, CPU). One model for EN + AR,
    # so an Arabic question can match an English record and vice versa.
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_cache_dir: str = str(DATA_DIR / "models")

    # Retrieval + scope gate. Score = cosine + name/path bonus, capped at 1.0.
    # Measured 2026-11-12 (scripts/query_vector_db.py): 16 CRM questions EN/AR scored
    # 0.74-1.00; off-topic questions scored 0.23-0.36. Re-check when the docs change.
    retrieval_top_k: int = 5
    scope_min_score: float = 0.45


@lru_cache
def get_settings() -> Settings:
    return Settings()
