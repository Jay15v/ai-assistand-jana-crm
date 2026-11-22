"""GeminiEmbedder tests with a fake API client (offline, no key, no quota used)."""

from types import SimpleNamespace

import pytest
from google.genai import errors

from app.core.config import Settings
from app.core.embeddings import DOCUMENT_TEMPLATE, QUERY_TEMPLATE, EmbeddingError, GeminiEmbedder
from app.features.agent.repositories.vector_store import VectorStore
from app.features.agent.schemas import CrmDoc

DIM = 4


class FakeModels:
    def __init__(self, fail_with=None, fail_times=0, drop_one=False, dim=DIM):
        self.calls = []
        self.fail_with, self.fail_times, self.drop_one, self.dim = fail_with, fail_times, drop_one, dim

    def embed_content(self, model, contents, config):
        texts = [c.parts[0].text for c in contents]
        self.calls.append({"model": model, "texts": texts, "dim": config.output_dimensionality})
        if self.fail_times > 0:
            self.fail_times -= 1
            raise self.fail_with
        n = len(texts) - (1 if self.drop_one else 0)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[float(i)] * self.dim) for i in range(n)])


def make(models=None, **kw):
    models = models or FakeModels()
    emb = GeminiEmbedder(
        api_key=None, model="gemini-embedding-2", dim=DIM, client=SimpleNamespace(models=models),
        sleep=lambda s: None, **kw,
    )
    return emb, models


def test_missing_key_gives_clear_error():
    with pytest.raises(EmbeddingError, match="GEMINI_API_KEY"):
        GeminiEmbedder(api_key=None, model="gemini-embedding-2", dim=DIM)


def test_one_vector_per_text_and_batches():
    emb, models = make(batch_size=2)
    vecs = emb.embed_documents(["a", "b", "c"], ["T1", None, "T3"])
    assert len(vecs) == 3 and all(len(v) == DIM for v in vecs)
    assert [len(c["texts"]) for c in models.calls] == [2, 1]  # split into batches of 2
    assert models.calls[0]["dim"] == DIM


def test_document_and_query_prompt_formats():
    emb, models = make()
    emb.embed_documents(["Refund screen"], ["Invoices > Refund"])
    emb.embed_query("  ازاي اعمل استرداد  ")
    assert models.calls[0]["texts"] == [DOCUMENT_TEMPLATE.format(title="Invoices > Refund", text="Refund screen")]
    assert models.calls[0]["texts"][0] == "title: Invoices > Refund | text: Refund screen"
    # Query: raw text (stripped, not normalized), with the search-task prefix.
    assert models.calls[1]["texts"] == [QUERY_TEMPLATE.format(text="ازاي اعمل استرداد")]


def test_missing_title_uses_none():
    emb, models = make()
    emb.embed_documents(["x"])
    assert models.calls[0]["texts"] == ["title: none | text: x"]


def test_query_cache_avoids_second_call():
    emb, models = make()
    emb.embed_query("add user")
    emb.embed_query("add user ")
    assert len(models.calls) == 1


def test_wrong_count_is_rejected():
    # gemini-embedding-2 merges a plain list into ONE vector; a short response must never pass silently.
    emb, _ = make(FakeModels(drop_one=True))
    with pytest.raises(EmbeddingError, match="expected 2 embeddings"):
        emb.embed_documents(["a", "b"])


def test_wrong_dimension_is_rejected():
    emb, _ = make(FakeModels(dim=DIM + 1))
    with pytest.raises(EmbeddingError, match="dimension"):
        emb.embed_documents(["a"])


def test_rate_limit_is_retried():
    emb, models = make(FakeModels(fail_with=errors.APIError(429, {}), fail_times=2), max_retries=3)
    assert len(emb.embed_documents(["a"])) == 1
    assert len(models.calls) == 3


def test_bad_request_is_not_retried():
    emb, models = make(FakeModels(fail_with=errors.APIError(400, {}), fail_times=5), max_retries=3)
    with pytest.raises(EmbeddingError):
        emb.embed_documents(["a"])
    assert len(models.calls) == 1


def test_retries_exhausted():
    emb, models = make(FakeModels(fail_with=errors.APIError(503, {}), fail_times=10), max_retries=2)
    with pytest.raises(EmbeddingError):
        emb.embed_documents(["a"])
    assert len(models.calls) == 3


# --- store safety ------------------------------------------------------------------------
DOC = {
    "id": "screen.x", "type": "screen", "group": {"en": "G", "ar": "ج"}, "screen": {"en": "X", "ar": "س"},
    "path": {"en": "G > X", "ar": "ج > س"}, "url": "https://h/en/x", "navigation_steps": [],
    "text_en": "Screen: X", "text_ar": "الشاشة: س",
}


def test_failed_rebuild_keeps_existing_db(tmp_path):
    settings = Settings(chroma_path=str(tmp_path / "c"), embedding_dim=DIM)
    good, _ = make()
    VectorStore(settings, embedder=good).rebuild([CrmDoc.model_validate(DOC)])

    broken, _ = make(FakeModels(fail_with=errors.APIError(400, {}), fail_times=99))
    with pytest.raises(EmbeddingError):
        VectorStore(settings, embedder=broken).rebuild([CrmDoc.model_validate(DOC)])
    assert VectorStore(settings, embedder=good).collection().count() == 4  # untouched


def test_model_mismatch_is_refused(tmp_path):
    good, _ = make()
    VectorStore(Settings(chroma_path=str(tmp_path / "c"), embedding_dim=DIM), embedder=good).rebuild(
        [CrmDoc.model_validate(DOC)]
    )
    other = VectorStore(Settings(chroma_path=str(tmp_path / "c"), embedding_dim=1536), embedder=good)
    with pytest.raises(RuntimeError, match="build_vector_db.py"):
        other.collection()
