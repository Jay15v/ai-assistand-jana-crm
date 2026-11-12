"""Try queries against the vector DB and print scores (use this to tune SCOPE_MIN_SCORE).

    python scripts/query_vector_db.py "how do I add a department"
    python scripts/query_vector_db.py            # runs the built-in EN/AR/off-topic sample set
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.vectordb.store import VectorStore  # noqa: E402

SAMPLES = [
    "how do I add a new department",
    "اضافة قسم جديد",
    "where can I block a unit",
    "حظر وحدة",
    "show me the invoices",
    "الفواتير",
    "create a ticket for a customer",
    "send a notification",
    "add a new user",
    # off-topic: should fall below the scope threshold
    "what is the weather today",
    "write me a poem about the sea",
    "ما هي عاصمة فرنسا",
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    store = VectorStore(get_settings())
    queries = sys.argv[1:] or SAMPLES
    for q in queries:
        r = store.search(q, top_k=3)
        flag = "IN " if r.in_scope else "OUT"
        print(f"[{flag}] {r.top_score:.3f} {r.latency_ms:>6}ms  {q}")
        for h in r.hits:
            print(f"        {h.score:.3f} ({h.matched_lang}) {h.doc.id:45} {h.doc.path.en}")


if __name__ == "__main__":
    main()
