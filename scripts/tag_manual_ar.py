"""Pair every ### question of the ARABIC manual with its English twin and inherit its tags.

    python scripts/tag_manual_ar.py   # writes data/manual/section_tabs_ar.json + prints the table

Pairing is positional (section i, question j in both manuals), which holds everywhere except the
two differences encoded in SKIP_EN below (EN questions with no Arabic twin - those sections are
answered from the English text when ui_lang=ar). The script fails loudly on any NEW mismatch, so
editing either manual later cannot silently break the pairing. Run scripts/tag_manual.py first.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EN_MANUAL = ROOT / "Ability_CRM_User_Manual.md"
AR_MANUAL = ROOT / "Ability_CRM_User_Manual_AR.md"
EN_TAGS = ROOT / "data" / "manual" / "section_tabs.json"
OUT = ROOT / "data" / "manual" / "section_tabs_ar.json"

# EN questions that have NO Arabic twin (checked by hand 2026-11-16). They are skipped during
# positional pairing of their section; ui_lang=ar answers for them come from the English chunk.
SKIP_EN = {
    "How do I create a ticket from a customer's page?",
    # The AR manual merges this one into its previous question
    # ("ازاي أعدل أو أوقف أو أمسح عنصر؟" covers delete + edit/deactivate; same tags either way).
    "How do I edit or deactivate a Definition item?",
}


def parse(path: Path) -> list[tuple[str, list[tuple[str, int]]]]:
    sections: list[tuple[str, list[tuple[str, int]]]] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif line.startswith("### ") and sections:
            sections[-1][1].append((line[4:].strip(), n))
    return sections


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    en_rows = {r["question"]: r for r in json.loads(EN_TAGS.read_text(encoding="utf-8"))}
    en_secs, ar_secs = parse(EN_MANUAL), parse(AR_MANUAL)
    if len(en_secs) != len(ar_secs):
        raise SystemExit(f"section count differs: EN {len(en_secs)} vs AR {len(ar_secs)}")

    rows, unpaired = [], []
    for (en_title, en_qs), (ar_title, ar_qs) in zip(en_secs, ar_secs):
        en_left = [(q, n) for q, n in en_qs if q not in SKIP_EN]
        if len(en_left) != len(ar_qs):
            raise SystemExit(
                f"MISMATCH in {en_title!r} vs {ar_title!r}: {len(en_left)} EN (after skips) "
                f"vs {len(ar_qs)} AR - fix SKIP_EN"
            )
        skipped = [q for q, _ in en_qs if q in SKIP_EN]
        unpaired += skipped
        for (en_q, _), (ar_q, ar_line) in zip(en_left, ar_qs):
            en_row = en_rows.get(en_q)
            if en_row is None:
                raise SystemExit(f"EN question not in section_tabs.json: {en_q!r}")
            rows.append({
                "section": ar_title, "question": ar_q, "line": ar_line,
                "general": en_row["general"], "tabs": en_row["tabs"], "require": en_row["require"],
                "en_question": en_q,
            })

    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} Arabic questions paired -> {OUT.relative_to(ROOT)}\n")
    cur = None
    for r in rows:
        if r["section"] != cur:
            cur = r["section"]
            print(f"## {cur}")
        tag = "general" if r["general"] else ", ".join(r["tabs"][:2]) + ("..." if len(r["tabs"]) > 2 else "")
        print(f"   {r['question'][:52]:54} = {r['en_question'][:48]:50} -> {tag}")
    print(f"\nEN questions with no Arabic twin (answered from English): {sorted(unpaired)}")


if __name__ == "__main__":
    main()
