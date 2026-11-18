"""Measure cosine-similarity score distributions of ManualIndex.search:
queries the manual DOES cover vs queries it does NOT. Admin permissions (all tabs
eligible) so the permission filter never interferes.

    python scripts/measure_manual_scores.py

Run after every manual update + re-index: the lowest COVERED score must stay
comfortably above settings.manual_min_score and the NOT_COVERED scores below it.
Add queries to the lists as the manual grows (and move ones that become covered).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.manual.index import ManualIndex  # noqa: E402
from app.scope.tabs import TabCatalog  # noqa: E402

COVERED = [
    "how do I search for tickets?",
    "How do I void an invoice directly?",
    "how do I collect payment for a pending invoice?",
    "how do I add a response to a complaint?",
    "ازاي ادور على شكوى؟",
    "ازاي الغي فاتورة؟",
    "how do i serch for tikets?",          # typos
    "ezay a3mel ticket gdeda?",            # franco-arabic
    "how do I check a tenant out?",
    "how do I review refund requests?",
    "how do I request a refund for an invoice?",   # covered since the 2026-11-18 refund sections
    "ازاي ارجع فلوس فاتورة للعميل؟",
    "how do I export the ticket search results to excel?",  # covered since the export section
]
NOT_COVERED = [
    "How do I send a push notification to customers on MyPorto?",
    "how do I change the dashboard theme color?",
    "how do I merge two duplicate customers?",
    "how do I set up two-factor authentication?",
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    settings = get_settings()
    catalog = TabCatalog.from_settings(settings)
    allowed = {t.name_en for t in catalog.tabs}
    index = ManualIndex(settings)
    for label, queries in (("COVERED", COVERED), ("NOT_COVERED", NOT_COVERED)):
        print(f"\n=== {label} ===")
        for q in queries:
            hits = index.search(q, allowed, top_k=2)
            shown = " | ".join(f"{s:.3f} {c.question_en}" for c, s in hits) or "(no hits)"
            print(f"{q}\n    {shown}")


if __name__ == "__main__":
    main()
