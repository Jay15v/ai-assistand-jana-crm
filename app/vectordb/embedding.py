"""Gemini embeddings (Google Gemini API, model gemini-embedding-2).

Vectors are computed here and passed to Chroma explicitly, so the collection never depends on
Chroma's built-in (English-only) model.

gemini-embedding-2 specifics (from Google's docs, 2026):
  * No `task_type` parameter. The task is written into the text instead:
        query    -> "task: search result | query: {text}"
        document -> "title: {title} | text: {text}"
  * A plain list of strings is merged into ONE embedding. To get one vector per text, each text
    is sent as its own Content object; the count is verified after every call.
  * Up to 8,192 input tokens per text; vectors are already normalized at every dimension.
"""

import logging
import time
from collections.abc import Callable, Sequence
from functools import lru_cache

log = logging.getLogger("crm_ai.embedding")

QUERY_TEMPLATE = "task: search result | query: {text}"
DOCUMENT_TEMPLATE = "title: {title} | text: {text}"
_RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}


class EmbeddingError(RuntimeError):
    """The embedding API could not produce vectors (missing key, bad response, retries exhausted)."""


class GeminiEmbedder:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        dim: int,
        batch_size: int = 50,
        timeout_s: float = 30.0,
        max_retries: int = 4,
        client=None,  # injected in tests
        sleep: Callable[[float], None] = time.sleep,
    ):
        from google.genai import types

        self._types = types
        if client is None:
            if not api_key:
                raise EmbeddingError(
                    "No Gemini API key. Put GEMINI_API_KEY=... (or GOOGLE_API_KEY=...) in the .env file "
                    "at the project root."
                )
            from google import genai

            client = genai.Client(
                api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000))
            )
        self._client = client
        self.model = model
        self.dim = dim
        self.batch_size = max(1, batch_size)
        self.max_retries = max_retries
        self._sleep = sleep
        self._query = lru_cache(maxsize=4096)(self._embed_query_uncached)

    # --- public ----------------------------------------------------------------------
    def embed_documents(self, texts: Sequence[str], titles: Sequence[str | None] | None = None) -> list[list[float]]:
        if titles is not None and len(titles) != len(texts):
            raise ValueError("titles must have the same length as texts")
        prepared = [
            DOCUMENT_TEMPLATE.format(title=(titles[i] if titles and titles[i] else "none"), text=t)
            for i, t in enumerate(texts)
        ]
        out: list[list[float]] = []
        for start in range(0, len(prepared), self.batch_size):
            out.extend(self._embed_batch(prepared[start : start + self.batch_size]))
        return out

    def embed_query(self, text: str) -> list[float]:
        # The raw text is embedded (not the normalize_text() form): the model understands
        # correctly spelled Arabic better than the matching-only normalized spelling.
        return list(self._query(text.strip()))

    # --- internals -------------------------------------------------------------------
    def _embed_query_uncached(self, text: str) -> tuple[float, ...]:
        return tuple(self._embed_batch([QUERY_TEMPLATE.format(text=text)])[0])

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        types = self._types
        contents = [types.Content(parts=[types.Part(text=t)]) for t in texts]  # one vector per text
        config = types.EmbedContentConfig(output_dimensionality=self.dim)
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                res = self._client.models.embed_content(model=self.model, contents=contents, config=config)
                break
            except Exception as exc:  # noqa: BLE001 - classified below
                if attempt >= self.max_retries or not _is_retryable(exc):
                    raise EmbeddingError(f"embedding request failed: {exc}") from exc
                wait = min(2.0**attempt, 20.0)
                log.warning("embedding retry %d/%d in %.0fs: %s", attempt + 1, self.max_retries, wait, exc)
                self._sleep(wait)
        vectors = [list(e.values or []) for e in (res.embeddings or [])]
        if len(vectors) != len(texts):
            raise EmbeddingError(f"expected {len(texts)} embeddings, got {len(vectors)}")
        bad = [len(v) for v in vectors if len(v) != self.dim]
        if bad:
            raise EmbeddingError(f"expected dimension {self.dim}, got {bad[0]}")
        log.debug("embedded %d texts in %.0f ms", len(texts), (time.perf_counter() - t0) * 1000)
        return vectors


def _is_retryable(exc: Exception) -> bool:
    from google.genai import errors

    if isinstance(exc, errors.APIError):
        return exc.code in _RETRYABLE_HTTP
    try:
        import httpx

        if isinstance(exc, httpx.TransportError):  # timeouts, connection resets, DNS
            return True
    except ImportError:  # pragma: no cover
        pass
    return isinstance(exc, (TimeoutError, ConnectionError))
