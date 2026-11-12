"""ChromaDB-backed CRM knowledge store.

Layout: four Chroma records per document: "<doc_id>::<en|ar>::<title|full>".
  * title - screen name, path, tabs and actions (short, matches "how do I add X" intents)
  * full  - the whole crawled page text (matches column / field / filter questions)
All are embedded with the same multilingual model, so a query in either language can hit
any record; results are merged back to one hit per document (best score wins).
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import chromadb

from app.config import Settings
from app.lang.normalize import STOPWORDS, normalize_text, search_tokens
from app.vectordb.embedding import Embedder
from app.vectordb.schema import CrmDoc, record_metadata, title_text

log = logging.getLogger("crm_ai.vectordb")

NAME_BONUS = 0.25  # added to the cosine score when the full screen name is in the query
PATH_BONUS = 0.10  # x share of query words found in the screen's navigation path
# Records fetched from Chroma before merging / re-ranking. The collection is small (~500
# records), so we score all of it: an exact name match must win even if the model ranked it low.
CANDIDATE_POOL = 1000
# Generic action words in screen names ("Add Role", "إضافة دور"). They say nothing about the
# subject, so they are ignored by the name match; otherwise "add X" would boost every "Add ..." screen.
GENERIC_NAME_WORDS = frozenset(
    {
        "add", "new", "create", "search", "edit", "delete", "view", "list", "details", "all",
        "اضافه", "جديد", "انشاء", "بحث", "تعديل", "حذف", "عرض", "تفاصيل", "الكل",
    }
)


@dataclass
class Hit:
    doc: CrmDoc
    score: float  # cosine similarity, higher is better
    matched_lang: str  # which language record matched


@dataclass
class SearchResult:
    hits: list[Hit] = field(default_factory=list)
    in_scope: bool = False
    top_score: float = 0.0
    latency_ms: float = 0.0


def load_docs(path: str | Path) -> list[CrmDoc]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw["documents"] if isinstance(raw, dict) else raw
    docs = [CrmDoc.model_validate(d) for d in items]
    ids = [d.id for d in docs]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate document ids: {sorted(dupes)}")
    return docs


class VectorStore:
    def __init__(self, settings: Settings, embedder: Embedder | None = None):
        self.settings = settings
        self.client = chromadb.PersistentClient(path=settings.chroma_path)
        self._embedder = embedder

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder(self.settings.embedding_model, self.settings.embedding_cache_dir)
        return self._embedder

    def collection(self):
        return self.client.get_collection(self.settings.chroma_collection)

    # --- build ---------------------------------------------------------------------
    def rebuild(self, docs: list[CrmDoc]) -> int:
        name = self.settings.chroma_collection
        if name in [c.name for c in self.client.list_collections()]:
            self.client.delete_collection(name)
        col = self.client.create_collection(
            name,
            embedding_function=None,  # vectors are supplied explicitly
            metadata={"hnsw:space": "cosine", "embedding_model": self.settings.embedding_model},
        )
        ids, texts, metas = [], [], []
        for d in docs:
            for lang, full in (("en", d.text_en), ("ar", d.text_ar)):
                for kind, text in (("title", title_text(d, lang)), ("full", full)):
                    if text and text.strip():
                        ids.append(f"{d.id}::{lang}::{kind}")
                        texts.append(text)
                        metas.append(record_metadata(d, lang, kind))
        vectors = self.embedder.embed_documents(texts)
        col.add(ids=ids, documents=texts, embeddings=vectors, metadatas=metas)
        return len(ids)

    # --- read ----------------------------------------------------------------------
    def search(
        self,
        query: str,
        top_k: int | None = None,
        allowed_hrefs: list[str] | None = None,
        types: list[str] | None = None,
    ) -> SearchResult:
        """Semantic search. `allowed_hrefs` restricts results to screens the user can open
        (the hook for the per-user tab cache); `types` restricts document types."""
        t0 = time.perf_counter()
        k = top_k or self.settings.retrieval_top_k
        where = _where(allowed_hrefs, types)
        col = self.collection()
        res = col.query(
            query_embeddings=[self.embedder.embed_query(query)],
            # Four records per doc (en/ar x title/full) are merged below; take a wide
            # candidate pool so the name-match bonus can lift a screen the model ranked lower.
            n_results=max(1, min(col.count(), CANDIDATE_POOL)),
            where=where,
            include=["metadatas", "distances"],
        )
        q_words = _query_words(query)
        best: dict[str, tuple[float, dict]] = {}
        for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
            # Semantic score + deterministic bilingual name/path evidence (spec priority 2).
            score = (
                1.0
                - float(dist)
                + NAME_BONUS * _name_match(q_words, meta)
                + PATH_BONUS * _path_coverage(q_words, meta)
            )
            doc_id = meta["doc_id"]
            if doc_id not in best or score > best[doc_id][0]:
                best[doc_id] = (score, meta)
        ranked = sorted(best.values(), key=lambda x: x[0], reverse=True)[:k]
        # Parse full documents only for the winners.
        hits = [Hit(CrmDoc.model_validate_json(m["doc_json"]), min(s, 1.0), m["lang"]) for s, m in ranked]
        top = hits[0].score if hits else 0.0
        result = SearchResult(
            hits=hits,
            in_scope=top >= self.settings.scope_min_score,
            top_score=top,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )
        log.info(
            "search q=%r in_scope=%s top=%.3f ms=%s hits=%s",
            query, result.in_scope, top, result.latency_ms,
            [(h.doc.id, round(h.score, 3)) for h in hits],
        )
        return result

    def get(self, doc_ids: list[str]) -> list[CrmDoc]:
        """Fetch documents by id (e.g. a hit's parent or next_step)."""
        if not doc_ids:
            return []
        res = self.collection().get(where={"doc_id": {"$in": doc_ids}}, include=["metadatas"])
        seen: dict[str, CrmDoc] = {}
        for meta in res["metadatas"]:
            seen.setdefault(meta["doc_id"], CrmDoc.model_validate_json(meta["doc_json"]))
        return [seen[i] for i in doc_ids if i in seen]

    def children(self, parent_id: str) -> list[CrmDoc]:
        """Tabs / forms / detail views that belong to a screen."""
        res = self.collection().get(
            where={"$and": [{"parent": parent_id}, {"lang": "en"}, {"kind": "full"}]}, include=["metadatas"]
        )
        return [CrmDoc.model_validate_json(m["doc_json"]) for m in res["metadatas"]]


def _content_words(text: str) -> list[set[str]]:
    """Each meaningful word of `text` as its set of normalized light-stem variants."""
    return [
        set(search_tokens(w))
        for w in normalize_text(text).split()
        if w not in STOPWORDS and w not in GENERIC_NAME_WORDS and len(w) > 1
    ]


def _query_words(query: str) -> list[set[str]]:
    return _content_words(query)


def _name_match(q_words: list[set[str]], meta: dict) -> float:
    """1.0 if every subject word of the screen name (EN or AR) appears in the query, else 0.
    Partial matches score nothing: sharing one word ("companies") is not evidence."""
    q_tokens = set().union(*q_words) if q_words else set()
    for key in ("screen_en", "screen_ar"):
        words = _content_words(meta.get(key, ""))
        if words and all(w & q_tokens for w in words):
            return 1.0
    return 0.0


def _path_coverage(q_words: list[set[str]], meta: dict) -> float:
    """Share of the query's words found in the navigation path (EN or AR). Breaks ties toward
    the more specific screen: "refund an invoice" -> "Invoices > Refund" over "Invoices"."""
    if not q_words:
        return 0.0
    best = 0.0
    for key in ("path_en", "path_ar"):
        path_tokens = set().union(*_content_words(meta.get(key, ""))) if meta.get(key) else set()
        if path_tokens:
            best = max(best, sum(1 for w in q_words if w & path_tokens) / len(q_words))
    return best


def _where(allowed_hrefs: list[str] | None, types: list[str] | None) -> dict | None:
    clauses = []
    if allowed_hrefs is not None:
        clauses.append({"href": {"$in": allowed_hrefs or ["__none__"]}})
    if types:
        clauses.append({"type": {"$in": types}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}
