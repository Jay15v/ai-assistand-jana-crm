"""Build the ChromaDB vector store in app/data/chroma from the crawled CRM documents.

    python scripts/build_vector_db.py

Rebuilds the collection from scratch each run (the source JSON is the source of truth).
"""

import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.vectordb.embedding import EmbeddingError  # noqa: E402
from app.vectordb.store import VectorStore, load_docs  # noqa: E402


def main() -> int:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(levelname)s %(name)s %(message)s")

    docs = load_docs(settings.vector_docs_path)
    print(f"Loaded {len(docs)} documents: {dict(Counter(d.type for d in docs))}")

    no_href = [d.id for d in docs if not d.href and d.type != "group"]
    if no_href:
        print(f"WARNING: {len(no_href)} non-group docs have no URL (cannot be matched by href): {no_href}")
    gaps = {d.id: d.missing_ar_labels() for d in docs if d.missing_ar_labels()}
    print(f"Arabic gaps: {len(gaps)} docs have {sum(gaps.values())} labels with no Arabic (kept as null)")

    print(f"Embedding with {settings.embedding_model} (dim {settings.embedding_dim}) via the Gemini API ...")
    try:
        n = VectorStore(settings).rebuild(docs)
    except EmbeddingError as exc:
        print(f"ERROR: {exc}\nThe existing vector DB was not changed.")
        return 1
    print(f"Chroma: {n} records -> {settings.chroma_path} (collection '{settings.chroma_collection}')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
