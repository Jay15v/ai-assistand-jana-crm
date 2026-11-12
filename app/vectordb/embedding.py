"""Local multilingual embeddings (fastembed / ONNX). Vectors are computed here and passed to
Chroma explicitly, so the collection never depends on Chroma's built-in (English-only) model."""

from functools import lru_cache

from app.lang.normalize import normalize_text


class Embedder:
    def __init__(self, model_name: str, cache_dir: str | None = None):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        self._query = lru_cache(maxsize=4096)(self._embed_one)

    def _embed_one(self, text: str) -> tuple[float, ...]:
        return tuple(float(x) for x in next(iter(self._model.embed([text]))))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in v] for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        # Cache on the normalized form so "Refund?" and "refund" share one vector.
        return list(self._query(normalize_text(text) or text))
