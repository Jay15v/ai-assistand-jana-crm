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

from app.core.config import Settings
from app.core.embeddings import GeminiEmbedder
from app.features.agent.schemas import CrmDoc, record_metadata, title_text

log = logging.getLogger("crm_ai.vectordb")

# Records fetched from Chroma before merging the 4 records of each document into one hit.
# The collection is small (~500 records), so all of it is fetched.
CANDIDATE_POOL = 1000


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
    def __init__(self, settings: Settings, embedder=None):
        self.settings = settings
        self.client = chromadb.PersistentClient(path=settings.chroma_path)
        self._embedder = embedder
        self._checked = False

    @property
    def embedder(self) -> GeminiEmbedder:
        if self._embedder is None:
            s = self.settings
            self._embedder = GeminiEmbedder(
                api_key=s.gemini_api_key.get_secret_value() if s.gemini_api_key else None,
                model=s.embedding_model,
                dim=s.embedding_dim,
                batch_size=s.embedding_batch_size,
                timeout_s=s.embedding_timeout_s,
                max_retries=s.embedding_max_retries,
            )
        return self._embedder

    def collection(self):
        col = self.client.get_collection(self.settings.chroma_collection)
        if not self._checked:
            # Query vectors are only comparable with vectors made by the same model + dimension.
            meta = col.metadata or {}
            built = (meta.get("embedding_model"), meta.get("embedding_dim"))
            wanted = (self.settings.embedding_model, self.settings.embedding_dim)
            if built != wanted:
                raise RuntimeError(
                    f"Vector DB was built with {built[0]} (dim {built[1]}) but the settings use "
                    f"{wanted[0]} (dim {wanted[1]}). Run: python scripts/build_vector_db.py"
                )
            self._checked = True
        return col

    # --- build ---------------------------------------------------------------------
    def rebuild(self, docs: list[CrmDoc]) -> int:
        ids, texts, titles, metas = [], [], [], []
        for d in docs:
            for lang, full in (("en", d.text_en), ("ar", d.text_ar)):
                for kind, text in (("title", title_text(d, lang)), ("full", full)):
                    if text and text.strip():
                        ids.append(f"{d.id}::{lang}::{kind}")
                        texts.append(text)
                        titles.append(getattr(d.path, lang) or d.path.en)
                        metas.append(record_metadata(d, lang, kind))
        # Embed FIRST: if the API fails, the existing collection is left untouched.
        vectors = self.embedder.embed_documents(texts, titles)

        name = self.settings.chroma_collection
        if name in [c.name for c in self.client.list_collections()]:
            self.client.delete_collection(name)
        col = self.client.create_collection(
            name,
            embedding_function=None,  # vectors are supplied explicitly
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": self.settings.embedding_model,
                "embedding_dim": self.settings.embedding_dim,
            },
        )
        col.add(ids=ids, documents=texts, embeddings=vectors, metadatas=metas)
        self._checked = True
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
            n_results=max(1, min(col.count(), CANDIDATE_POOL)),
            where=where,
            include=["metadatas", "distances"],
        )
        best: dict[str, tuple[float, dict]] = {}
        for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
            score = 1.0 - float(dist)  # cosine similarity from Gemini, nothing added
            doc_id = meta["doc_id"]
            if doc_id not in best or score > best[doc_id][0]:
                best[doc_id] = (score, meta)
        ranked = sorted(best.values(), key=lambda x: x[0], reverse=True)[:k]
        # Parse full documents only for the winners.
        hits = [Hit(CrmDoc.model_validate_json(m["doc_json"]), s, m["lang"]) for s, m in ranked]
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


def _where(allowed_hrefs: list[str] | None, types: list[str] | None) -> dict | None:
    clauses = []
    if allowed_hrefs is not None:
        clauses.append({"href": {"$in": allowed_hrefs or ["__none__"]}})
    if types:
        clauses.append({"type": {"$in": types}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}
