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

    # Chat memory. Production: set DATABASE_URL (Postgres) in .env and the checkpointer switches
    # automatically; unset -> in-memory (history lost on restart; fine for dev and tests).
    database_url: str | None = Field(default=None, validation_alias=AliasChoices("DATABASE_URL"))
    history_keep_turns: int = 6  # turns kept verbatim after compaction
    compact_after_turns: int = 8  # compact when history grows beyond this

    # Chat LLM (scope decision now, answer generation in step 3). Same Gemini key as embeddings.
    llm_model: str = "gemini-2.5-flash"
    llm_temperature: float = 0.0  # deterministic: same question -> same decision
    llm_timeout_s: float = 20.0
    llm_max_retries: int = 2

    # Retrieval + scope gate. Score = Gemini cosine similarity only (no bonuses).
    # NOTE: 0.45 was measured with the previous local model (MiniLM). Gemini scores sit on a
    # different scale, so re-measure with scripts/query_vector_db.py after the first Gemini build.
    retrieval_top_k: int = 5
    scope_min_score: float = 0.45

    # Manual retrieval floor (crm_manual index): hits below this cosine similarity are dropped,
    # so unanswerable questions route to the no-docs reply instead of feeding the generator a
    # wrong-but-nearest section. Measured 2026-11-18 with gemini-embedding-2/3072: covered
    # questions score >= 0.79, clearly-unrelated <= 0.70. Re-measure as the manual grows.
    manual_min_score: float = 0.72


@lru_cache
def get_settings() -> Settings:
    return Settings()
