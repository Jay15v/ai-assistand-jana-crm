"""Build (or rebuild) the crm_manual index from the two manuals. Rerun after editing a manual
(run tag_manual.py / tag_manual_ar.py first if headings changed).

    python scripts/build_manual_index.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.manual.chunks import load_chunks  # noqa: E402
from app.manual.index import ManualIndex  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    chunks = load_chunks()
    with_ar = sum(1 for c in chunks if c.text_ar)
    print(f"chunks: {len(chunks)} ({with_ar} with Arabic twin, {len(chunks) - with_ar} EN-only)")
    n = ManualIndex(get_settings()).rebuild(chunks)
    print(f"indexed {n} records into 'crm_manual'")


if __name__ == "__main__":
    main()
