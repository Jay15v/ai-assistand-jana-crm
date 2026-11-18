"""Collect the tab tags of every ### question of the English manual FROM THE MANUAL ITSELF.

    python scripts/tag_manual.py          # writes app/data/manual/section_tabs.json + prints the table

The manual is the single source of truth: tags live in HTML comments inside the MD file and
this script only parses, validates and exports them. Two comment forms, each on the first
line after its heading:

    ## 12. Invoices
    <!-- tabs: Search Invoices -->                    section default: applies to every ###
                                                      question below that has no own comment
    <!-- tabs: general -->                            section default: general (login, glossary,
                                                      troubleshooting... belongs to no tab)
    ### How do I create a ticket from a customer's page?
    <!-- tabs: Search Customer, Add Ticket | require: all -->
                                                      per-question tag; "require: all" marks a
                                                      flow that needs EVERY listed tab

Tags use the vector DB's English tab names (the same 54 names step 1 matches against).
The script fails loudly on any untagged question and any tab name outside the catalog, so
editing the manual cannot silently break the tagging. The comments never reach the index or
the user: app/manual/chunks.py strips comment lines from the section bodies.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.scope.tabs import TabCatalog  # noqa: E402

MANUAL = ROOT / "Ability_CRM_User_Manual.md"
OUT = ROOT / "app" / "data" / "manual" / "section_tabs.json"

TAG_COMMENT = re.compile(r"^\s*<!--\s*tabs:\s*(.+?)\s*-->\s*$")


def parse_tag(text: str, where: str) -> tuple[list[str], str, bool]:
    """'A, B | require: all' -> (tabs, require, general)."""
    parts = [p.strip() for p in text.split("|")]
    require = "any"
    for opt in parts[1:]:
        if re.fullmatch(r"require\s*:\s*all", opt):
            require = "all"
        else:
            raise SystemExit(f"bad tag option {opt!r} in {where}")
    if parts[0].lower() == "general":
        return [], require, True
    return [t.strip() for t in parts[0].split(",") if t.strip()], require, False


def parse_manual() -> list[dict]:
    """One row per ### question; the tag comment must be the first line after its heading."""
    rows: list[dict] = []
    section = None
    sec_default: tuple[list[str], bool] | None = None  # (tabs, general) from the ## comment
    pending: dict | None = None  # last ### row, until its own comment (or the next heading)

    def close_pending() -> None:
        nonlocal pending
        if pending is None:
            return
        if pending["tabs"] is None:  # no own comment: fall back to the section default
            if sec_default is None:
                raise SystemExit(f"UNTAGGED question (line {pending['line']}): "
                                 f"{pending['question']!r} in section {section!r}")
            pending["tabs"], pending["general"] = sec_default
        rows.append(pending)
        pending = None

    for n, line in enumerate(MANUAL.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            close_pending()
            section = line[3:].strip()
            sec_default = None
            expect = "section"
        elif line.startswith("### ") and section:
            close_pending()
            pending = {"section": section, "question": line[4:].strip(), "line": n,
                       "general": False, "tabs": None, "require": "any"}
            expect = "question"
        elif (m := TAG_COMMENT.match(line)):
            tabs, require, general = parse_tag(m.group(1), f"line {n}")
            if expect == "section":
                sec_default = (tabs, general)
            elif expect == "question" and pending is not None:
                pending["tabs"], pending["require"], pending["general"] = tabs, require, general
            else:
                raise SystemExit(f"tag comment on line {n} follows no heading")
            expect = None
        elif line.strip():
            expect = None  # body text: a later comment in this section is not a tag
    close_pending()
    return rows


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    catalog = TabCatalog.from_settings(get_settings())
    valid = {t.name_en for t in catalog.tabs}
    rows = parse_manual()

    bad = [(r["question"], t) for r in rows for t in r["tabs"] if t not in valid]
    if bad:
        raise SystemExit(f"tags not in the {len(valid)}-tab catalog: {bad}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    covered: dict[str, int] = {}
    for r in rows:
        for t in r["tabs"]:
            covered[t] = covered.get(t, 0) + 1
    print(f"{len(rows)} questions tagged -> {OUT.relative_to(ROOT)}\n")
    cur = None
    for r in rows:
        if r["section"] != cur:
            cur = r["section"]
            print(f"## {cur}")
        tag = "general" if r["general"] else ", ".join(r["tabs"])
        print(f"   {r['question']:70} -> {tag}")
    uncovered = sorted(valid - set(covered))
    print(f"\ntabs with manual questions: {len(covered)}/{len(valid)}")
    print(f"tabs WITHOUT a manual question (bare-name description in part B): {uncovered}")


if __name__ == "__main__":
    main()
