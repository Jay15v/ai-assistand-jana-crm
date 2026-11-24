"""Build (or rebuild) the crm_manual index from the two manuals. Rerun after editing a manual
(run tag_manual.py / tag_manual_ar.py first if headings changed).

    python scripts/build_manual_index.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.features.agent.repositories.manual import ManualIndex, load_chunks  # noqa: E402
from app.features.agent.repositories.tabs import TabCatalog  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    settings = get_settings()
    chunks = load_chunks()
    with_ar = sum(1 for c in chunks if c.text_ar)
    shared = sum(1 for c in chunks if c.is_shared())
    print(f"chunks: {len(chunks)} ({with_ar} with Arabic twin, {len(chunks) - with_ar} EN-only, "
          f"{shared} shared by several tabs)")
    n = ManualIndex(settings).rebuild(chunks, TabCatalog.from_settings(settings))
    print(f"indexed {n} records into 'crm_manual'")


if __name__ == "__main__":
    main()
