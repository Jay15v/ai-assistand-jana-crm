"""The user manuals as data: parsing them into chunks, and the ChromaDB index built from those chunks."""

import json
import logging
import re
import time
from pathlib import Path

import chromadb
from pydantic import BaseModel

from app.core.config import DATA_DIR, ROOT_DIR, Settings
from app.core.embeddings import GeminiEmbedder
from app.features.agent.repositories.tabs import TabCatalog

# --------------------------------------------------------------------------------------------------
# Chunks
#
# Parse the EN + AR user manuals into answer chunks (one per ### question).
#
# Each chunk carries the English section text, its Arabic twin's text (when the AR manual has one),
# the intro of its chapter (the text between the "## " heading and the first "### " question:
# purpose, menu path, and tables such as the fields of every Definition page - facts the questions
# below it rely on without repeating them), and the tags from data/manual/section_tabs(.ar).json.
# Image lines and HTML comment lines
# (the <!-- tabs: ... --> tags that tag_manual.py parses) are stripped - both are internal
# reference material and never reach the index or the user.
# --------------------------------------------------------------------------------------------------

EN_MANUAL = ROOT_DIR / "Ability_CRM_User_Manual.md"
AR_MANUAL = ROOT_DIR / "Ability_CRM_User_Manual_AR.md"
EN_TAGS = DATA_DIR / "manual" / "section_tabs.json"
AR_TAGS = DATA_DIR / "manual" / "section_tabs_ar.json"

_IMAGE_LINE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")
_INLINE_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_COMMENT_LINE = re.compile(r"^\s*<!--.*-->\s*$")
_RULE_LINE = re.compile(r"^\s*-{3,}\s*$")  # a markdown horizontal rule (layout only)


class ManualChunk(BaseModel):
    id: str  # stable within one build, e.g. "manual.0291" (EN manual line of the ### heading)
    section_en: str  # the ## menu header, e.g. "12. Invoices"
    question_en: str
    question_ar: str | None  # None for the 2 EN questions with no Arabic twin
    text_en: str  # "### question\n" + body, images stripped
    text_ar: str | None
    intro_en: str = ""  # the chapter intro above the questions ("" when the chapter has none)
    intro_ar: str = ""
    tabs: list[str]  # English tab names (step 1's vocabulary); [] for general
    require: str  # "any" | "all"
    general: bool

    def title_text(self) -> str:
        """The bilingual record embedded for intent matching (option C)."""
        return f"{self.question_en} | {self.question_ar}" if self.question_ar else self.question_en

    def is_shared(self) -> bool:
        """One section written once for several tabs (e.g. 'add a Definition item' serves every
        Definition list). Its question is generic, so it names none of those tabs."""
        return not self.general and len(self.tabs) > 1

    def text(self, lang: str) -> str:
        """The answer source for a reply language; EN is the fallback (confirmed behavior)."""
        return self.text_ar if lang == "ar" and self.text_ar else self.text_en

    def intro(self, lang: str) -> str:
        """The chapter intro in the SAME language as text(lang), so one answer never mixes an
        Arabic section with English background. May be ""."""
        return self.intro_ar if lang == "ar" and self.text_ar else self.intro_en


def _strip_images(body: str) -> str:
    lines = [
        ln for ln in body.splitlines()
        if not _IMAGE_LINE.match(ln) and not _COMMENT_LINE.match(ln)
    ]
    return _INLINE_IMAGE.sub("", "\n".join(lines)).strip()


def _strip_intro(lines: list[str]) -> str:
    return _strip_images("\n".join(ln for ln in lines if not _RULE_LINE.match(ln)))


def _section_bodies(path: Path) -> dict[str, tuple[int, str, str]]:
    """{### question: (line number, stripped body text, intro of its ## chapter)} for one manual."""
    out: dict[str, tuple[int, str, str]] = {}
    current: tuple[str, int] | None = None
    buf: list[str] = []
    intro = ""  # of the chapter being read; fixed once its first ### question starts
    intro_buf: list[str] | None = None  # None = not between a ## heading and its first ###

    def flush() -> None:
        if current:
            q, n = current
            out[q] = (n, _strip_images("\n".join(buf)), intro)

    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            flush()
            current, buf, intro, intro_buf = None, [], "", []
        elif line.startswith("### "):
            flush()
            if intro_buf is not None:
                intro, intro_buf = _strip_intro(intro_buf), None
            current, buf = (line[4:].strip(), n), []
        elif current:
            buf.append(line)
        elif intro_buf is not None:
            intro_buf.append(line)
    flush()
    return out


def load_chunks() -> list[ManualChunk]:
    en_rows = json.loads(EN_TAGS.read_text(encoding="utf-8"))
    ar_by_en = {r["en_question"]: r for r in json.loads(AR_TAGS.read_text(encoding="utf-8"))}
    en_bodies = _section_bodies(EN_MANUAL)
    ar_bodies = _section_bodies(AR_MANUAL)

    chunks: list[ManualChunk] = []
    for row in en_rows:
        q = row["question"]
        line, body, intro = en_bodies[q]
        ar_row = ar_by_en.get(q)
        ar_q = ar_row["question"] if ar_row else None
        ar_body = ar_bodies.get(ar_q) if ar_q else None
        chunks.append(ManualChunk(
            id=f"manual.{line:04d}",
            section_en=row["section"],
            question_en=q,
            question_ar=ar_q,
            text_en=f"### {q}\n{body}",
            text_ar=f"### {ar_q}\n{ar_body[1]}" if ar_body else None,
            intro_en=intro,
            intro_ar=ar_body[2] if ar_body else "",
            tabs=row["tabs"],
            require=row.get("require", "any"),
            general=row["general"],
        ))
    return chunks


# --------------------------------------------------------------------------------------------------
# Index
#
# ChromaDB index of the manual chunks (option C).
#
# Records per chunk, all pointing at the same chunk JSON:
#   * "<id>::title" - the EN question + its AR twin glued together: direct hits in both languages
#   * "<id>::full"  - the whole English section: catches detail questions about fields/filters
#   * "<id>::tab<n>" - SHARED chunks only (tagged with several tabs): one record per tab, the tab's
#     EN + AR names in front of the question. A shared section's question is generic ("add a
#     Definition item"), while users ask with the tab's own word ("add a rental company"); without
#     this record the nearest match is another tab's section that merely shares a word.
# Search merges records per chunk (best score wins), then the PERMISSION FILTER keeps only chunks
# the user's allowed tabs justify. General chunks are never retrieved (scope routes them off_topic
# before retrieval). The crawl collection (crm_knowledge) is untouched.
# --------------------------------------------------------------------------------------------------

log = logging.getLogger("crm_ai.manual")

COLLECTION = "crm_manual"
CANDIDATE_POOL = 300  # the collection is tiny; fetch everything and rank in Python


class IndexRecord(BaseModel):
    """One embedded row of the index. `title` goes into the embedding's title slot."""

    id: str
    kind: str  # "title" | "full" | "tab"
    chunk_id: str
    title: str
    text: str


def index_records(chunks: list[ManualChunk], catalog: TabCatalog) -> list[IndexRecord]:
    """Every record to embed for these chunks. Tab names come from the catalog (the same tab
    list step 1 uses), so a tab renamed or added in the CRM needs a re-index, never a code change."""
    tabs_by_name = {t.name_en: t for t in catalog.tabs}
    records: list[IndexRecord] = []
    for c in chunks:
        records.append(IndexRecord(
            id=f"{c.id}::title", kind="title", chunk_id=c.id, title=c.question_en, text=c.title_text()))
        records.append(IndexRecord(
            id=f"{c.id}::full", kind="full", chunk_id=c.id, title=c.question_en, text=c.text_en))
        if not c.is_shared():
            continue
        for n, name in enumerate(c.tabs):
            tab = tabs_by_name.get(name)
            if tab is None:  # tag_manual.py validates tags against the catalog; defensive only
                log.warning("chunk %s is tagged with unknown tab %r - no tab record", c.id, name)
                continue
            records.append(IndexRecord(
                id=f"{c.id}::tab{n}", kind="tab", chunk_id=c.id, title=tab.name_en,
                text=f"{tab.name_en} ({tab.name_ar}): {c.title_text()}",
            ))
    return records


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

    def rebuild(self, chunks: list[ManualChunk], catalog: TabCatalog) -> int:
        chunk_json = {c.id: c.model_dump_json() for c in chunks}
        records = index_records(chunks, catalog)
        ids = [r.id for r in records]
        texts = [r.text for r in records]
        titles = [r.title for r in records]
        metas = [{"chunk_id": r.chunk_id, "kind": r.kind, "chunk_json": chunk_json[r.chunk_id]} for r in records]
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
        """Best eligible chunks for this query, (chunk, cosine similarity), best first.

        Hits scoring below settings.manual_min_score are dropped: an empty result means the
        manual has no section close enough, and the graph routes to the no-docs reply."""
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
            if score < self.settings.manual_min_score:
                break  # sorted best-first: everything after this is weaker
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
