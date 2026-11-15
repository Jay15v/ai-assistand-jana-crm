"""Environment-driven configuration for the vector DB layer. Values come from .env (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
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

    # Embeddings: Google Gemini API. One multilingual model for EN + AR, so an Arabic question can
    # match an English record and vice versa. Accepts GEMINI_API_KEY or GOOGLE_API_KEY from .env.
    gemini_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY")
    )
    embedding_model: str = "gemini-embedding-2"
    # 3072 = the model's full size (best quality); 1536 / 768 are smaller with a small quality loss.
    # Changing the model or the dimension requires a rebuild (scripts/build_vector_db.py).
    embedding_dim: int = 3072
    embedding_batch_size: int = 50  # texts per API request when building the DB
    embedding_timeout_s: float = 30.0  # per API request
    embedding_max_retries: int = 4  # on rate limits (429), server errors (5xx) and network errors

    # Retrieval + scope gate. Score = Gemini cosine similarity only (no bonuses).
    # NOTE: 0.45 was measured with the previous local model (MiniLM). Gemini scores sit on a
    # different scale, so re-measure with scripts/query_vector_db.py after the first Gemini build.
    retrieval_top_k: int = 5
    scope_min_score: float = 0.45


@lru_cache
def get_settings() -> Settings:
    return Settings()
