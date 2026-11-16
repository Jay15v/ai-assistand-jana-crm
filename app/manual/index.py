"""ChromaDB index of the manual chunks (option C).

Two records per chunk, both pointing at the same chunk JSON:
  * "<id>::title" - the EN question + its AR twin glued together: direct hits in both languages
  * "<id>::full"  - the whole English section: catches detail questions about fields/filters
Search merges records per chunk (best score wins), then the PERMISSION FILTER keeps only chunks
the user's allowed tabs justify. General chunks are never retrieved (scope routes them off_topic
before retrieval). The crawl collection (crm_knowledge) is untouched.
"""

import logging
import time

import chromadb

from app.config import Settings
from app.manual.chunks import ManualChunk
from app.vectordb.embedding import GeminiEmbedder

log = logging.getLogger("crm_ai.manual")

COLLECTION = "crm_manual"
CANDIDATE_POOL = 300  # the collection is tiny; fetch everything and rank in Python


def eligible(chunk: ManualChunk, allowed_names: set[str]) -> bool:
    """May this user see this chunk? (the security filter)"""
    if chunk.general or not chunk.tabs:
        return False
    if chunk.require == "all":
        return set(chunk.tabs) <= allowed_names
    return bool(set(chunk.tabs) & allowed_names)


class ManualIndex:
    def __init__(self, settings: Settings, embedder: GeminiEmbedder | None = None):
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
        col = self.client.get_collection(COLLECTION)
        if not self._checked:
            meta = col.metadata or {}
            built = (meta.get("embedding_model"), meta.get("embedding_dim"))
            wanted = (self.settings.embedding_model, self.settings.embedding_dim)
            if built != wanted:
                raise RuntimeError(
                    f"{COLLECTION} was built with {built} but settings use {wanted}. "
                    "Run: python scripts/build_manual_index.py"
                )
            self._checked = True
        return col

    def rebuild(self, chunks: list[ManualChunk]) -> int:
        ids, texts, titles, metas = [], [], [], []
        for c in chunks:
            for kind, text in (("title", c.title_text()), ("full", c.text_en)):
                ids.append(f"{c.id}::{kind}")
                texts.append(text)
                titles.append(c.question_en)
                metas.append({"chunk_id": c.id, "kind": kind, "chunk_json": c.model_dump_json()})
        vectors = self.embedder.embed_documents(texts, titles)  # embed FIRST: failure keeps old index
        if COLLECTION in [c.name for c in self.client.list_collections()]:
            self.client.delete_collection(COLLECTION)
        col = self.client.create_collection(
            COLLECTION,
            embedding_function=None,
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": self.settings.embedding_model,
                "embedding_dim": self.settings.embedding_dim,
            },
        )
        col.add(ids=ids, documents=texts, embeddings=vectors, metadatas=metas)
        self._checked = True
        return len(ids)

    def search(self, query: str, allowed_names: set[str], top_k: int = 3) -> list[tuple[ManualChunk, float]]:
        """Best eligible chunks for this query, (chunk, cosine similarity), best first."""
        t0 = time.perf_counter()
        col = self.collection()
        res = col.query(
            query_embeddings=[self.embedder.embed_query(query)],
            n_results=max(1, min(col.count(), CANDIDATE_POOL)),
            include=["metadatas", "distances"],
        )
        best: dict[str, tuple[float, dict]] = {}
        for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
            score = 1.0 - float(dist)
            cid = meta["chunk_id"]
            if cid not in best or score > best[cid][0]:
                best[cid] = (score, meta)
        hits: list[tuple[ManualChunk, float]] = []
        for score, meta in sorted(best.values(), key=lambda x: x[0], reverse=True):
            chunk = ManualChunk.model_validate_json(meta["chunk_json"])
            if eligible(chunk, allowed_names):
                hits.append((chunk, score))
            if len(hits) >= top_k:
                break
        log.info(
            "manual search q=%r hits=%s ms=%.0f",
            query, [(c.id, round(s, 3)) for c, s in hits], (time.perf_counter() - t0) * 1000,
        )
        return hits
