"""Part B of the scope flow: one short description per tab, for the LLM scope prompt.

Single source: the MD manual. tag_manual.py parses the manual's ### questions, attaches the
hand-reviewed tab tags and writes app/data/manual/section_tabs.json; each tab's description is
the list of its manual questions - they say what a user can actually DO in the tab ("void an
invoice directly", "change a ticket's status"), which is what lets the LLM match free wording
like "cancel a bill". A tab with no manual section yet (currently only Notifications) falls
back to its bare name.

A question tagged require="all" appears in each of its tabs with an "(also requires: ...)" note;
the prompt tells the LLM such flows are allowed only when every named tab is in the allowed list.
"""

import json
from pathlib import Path

from app.config import ROOT_DIR
from app.scope.tabs import Tab, TabCatalog

SECTION_TABS_PATH = ROOT_DIR / "app" / "data" / "manual" / "section_tabs.json"


def build_descriptions(catalog: TabCatalog, tags_path: Path | None = None) -> dict[str, str]:
    """Return {tab doc_id: one-line description} for all tabs, from the manual's questions."""
    rows = json.loads((tags_path or SECTION_TABS_PATH).read_text(encoding="utf-8"))
    by_name = {t.name_en: t for t in catalog.tabs}

    lines: dict[str, list[str]] = {}
    for row in rows:
        if row["general"] or not row["tabs"]:
            continue
        for name in row["tabs"]:
            tab = by_name.get(name)
            if tab is None:  # tag_manual.py already validates; defensive only
                continue
            text = row["question"].rstrip("?")
            if row.get("require") == "all" and len(row["tabs"]) > 1:
                others = ", ".join(f"'{t}'" for t in row["tabs"] if t != name)
                text += f" (also requires: {others})"
            lines.setdefault(tab.doc_id, []).append(text)

    return {
        tab.doc_id: "; ".join(lines[tab.doc_id]) if tab.doc_id in lines else tab.name_en
        for tab in catalog.tabs
    }


def format_tab_list(tabs: list[Tab], descriptions: dict[str, str]) -> str:
    """One prompt line per tab: 'Menu > Tab (AR name): description'."""
    if not tabs:
        return "(none)"
    return "\n".join(
        f"- {t.menu_en} > {t.name_en} ({t.name_ar}): {descriptions.get(t.doc_id, t.name_en)}"
        for t in tabs
    )
