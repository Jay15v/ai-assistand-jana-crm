"""Vector DB tests. Run offline with a deterministic bag-of-words embedder (no model download)."""

import hashlib
import math

import pytest

from app.core.config import Settings
from app.core.normalize import search_tokens
from app.features.agent.repositories.vector_store import VectorStore, load_docs
from app.features.agent.schemas import CrmDoc, href_from_url, title_text


class FakeEmbedder:
    dim = 256

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in search_tokens(text):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts, titles=None):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def _doc(id_, en, ar, group_en, group_ar, url, actions=()):
    return {
        "id": id_,
        "type": "screen",
        "group": {"en": group_en, "ar": group_ar},
        "screen": {"en": en, "ar": ar},
        "path": {"en": f"{group_en} > {en}", "ar": f"{group_ar} > {ar}"},
        "url": url,
        "actions": [{"en": a, "ar": None} for a in actions],
        "navigation_steps": [],
        "text_en": f"Screen: {en}\nNavigation path: {group_en} > {en}",
        "text_ar": f"الشاشة: {ar}\nمسار التنقل: {group_ar} > {ar}",
    }


DOCS = [
    _doc("screen.definition.department", "Department", "القسم", "Definition", "التعريفات",
         "https://app.ability-tech.com/en/definitions/department", ["Add"]),
    _doc("screen.roles.add_role", "Add Role", "إضافة دور", "Roles", "الأدوار",
         "https://app.ability-tech.com/en/roles/add"),
    _doc("screen.invoices.refund", "Refund", "استرداد", "Invoices", "الفواتير",
         "https://app.ability-tech.com/en/invoices/refund"),
]


@pytest.fixture
def store(tmp_path):
    settings = Settings(chroma_path=str(tmp_path / "chroma"), scope_min_score=0.3)
    s = VectorStore(settings, embedder=FakeEmbedder())
    s.rebuild([CrmDoc.model_validate(d) for d in DOCS])
    return s


# --- schema ------------------------------------------------------------------------
def test_href_strips_host_and_locale():
    assert href_from_url("https://app.ability-tech.com/en/definitions/department") == "/definitions/department"
    assert href_from_url("https://app.ability-tech.com/ar/units/{unit_id}") == "/units/{unit_id}"
    assert href_from_url(None) is None


def test_missing_arabic_is_counted_not_invented():
    d = CrmDoc.model_validate(DOCS[0])
    assert d.missing_ar_labels() == 1  # the "Add" action has no Arabic
    assert "None" not in title_text(d, "ar")


def test_real_source_file_loads():
    docs = load_docs(Settings().vector_docs_path)
    assert len(docs) == 119
    assert all(d.text_en and d.text_ar for d in docs)


# --- store -------------------------------------------------------------------------
def test_english_and_arabic_hit_same_canonical_doc(store):
    en = store.search("how do I add a new department")
    ar = store.search("اضافة قسم جديد")
    assert en.hits[0].doc.id == ar.hits[0].doc.id == "screen.definition.department"


def test_off_topic_is_out_of_scope(store):
    assert not store.search("what is the weather today").in_scope


def test_allowed_hrefs_limits_results_to_user_screens(store):
    r = store.search("department", allowed_hrefs=["/roles/add", "/invoices/refund"])
    assert all(h.doc.href in {"/roles/add", "/invoices/refund"} for h in r.hits)
    assert "screen.definition.department" not in [h.doc.id for h in r.hits]


def test_empty_allowed_hrefs_returns_nothing(store):
    assert store.search("department", allowed_hrefs=[]).hits == []


def test_one_hit_per_document(store):
    ids = [h.doc.id for h in store.search("refund invoice").hits]
    assert len(ids) == len(set(ids))


def test_get_by_id(store):
    assert [d.id for d in store.get(["screen.invoices.refund"])] == ["screen.invoices.refund"]
