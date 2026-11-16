"""Part B of the scope flow: one short description per tab, for the LLM scope prompt.

Main source  : the manual's tagged questions (app/data/manual/section_tabs.json) - they say what a
               user can actually DO in the tab ("void an invoice directly", "change a ticket's
               status"), which is what lets the LLM match free wording like "cancel a bill".
Fallback     : for tabs without a manual section yet, the crawled screen text from the vector DB
               (title_text: screen name, path, visible actions) - weaker, but enough for the LLM
               to recognise the tab and judge allowed / not_allowed.

A question tagged require="all" appears in each of its tabs with an "(also requires: ...)" note;
the prompt tells the LLM such flows are allowed only when every named tab is in the allowed list.
"""

import json
from pathlib import Path

from app.config import ROOT_DIR, Settings
from app.scope.tabs import Tab, TabCatalog
from app.vectordb.schema import title_text
from app.vectordb.store import load_docs

SECTION_TABS_PATH = ROOT_DIR / "app" / "data" / "manual" / "section_tabs.json"

# Hand-written purpose lines for the tabs that have no manual section AND a thin crawl text.
# Wording grounded in the menu names and the endpoint's privilege names (e.g. Refund carries
# "Accept Refund Request" / "Reject Refund Request"; Unit Blocks carries "Finance Block",
# "Legal Block", "UnBlock"). Replace with manual questions once those sections are written.
TAB_NOTES: dict[str, str] = {
    "Add Block": "block a unit (finance block or legal block) so it cannot be rented or transacted",
    "Search Block": "find blocked units and unblock a unit",
    "Add Legal Users": "create a legal-department user account",
    "Manage Legal Users": "find, edit or deactivate legal-department users",
    "Add Request": "register a new unit ownership transfer request",
    "Search Request": "find ownership transfer requests; close or invalidate a request",
    "Import Customers": "bulk-import customers from an uploaded file",
    "Import History": "see past bulk imports and their results",
    "Import Relatives": "bulk-import owner relatives from an uploaded file",
    "Import Units": "bulk-import units from an uploaded file",
    "Notifications": "send a notification message to customers (MyPorto app push notifications)",
    "Refund": "review invoice refund and void requests; accept or reject them",
    "Relative Requests": "review customers' relative requests; accept or reject them",
}


def build_descriptions(
    catalog: TabCatalog, settings: Settings, tags_path: Path | None = None
) -> dict[str, str]:
    """Return {tab doc_id: one-line description} for all 54 tabs."""
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

    docs = {d.id: d for d in load_docs(settings.vector_docs_path)}
    out: dict[str, str] = {}
    for tab in catalog.tabs:
        parts = []
        if tab.doc_id in lines:
            parts.append("; ".join(lines[tab.doc_id]))
        if tab.name_en in TAB_NOTES:
            parts.append(TAB_NOTES[tab.name_en])
        if not parts:  # no manual section and no note: fall back to the crawled screen text
            doc = docs.get(tab.doc_id)
            actions = _crawl_actions(doc) if doc else []
            if actions:
                parts.append("screen controls: " + ", ".join(actions))
            else:
                parts.append(title_text(doc, "en") if doc else tab.name_en)
        out[tab.doc_id] = " | ".join(parts)
    return out


def _crawl_actions(doc) -> list[str]:
    """English action labels crawled from the screen (e.g. Search, Clear, Export to Excel)."""
    extra = doc.model_extra or {}
    return [a["en"] for a in extra.get("actions") or [] if isinstance(a, dict) and a.get("en")]


def format_tab_list(tabs: list[Tab], descriptions: dict[str, str]) -> str:
    """One prompt line per tab: 'Menu > Tab (AR name): description'."""
    if not tabs:
        return "(none)"
    return "\n".join(
        f"- {t.menu_en} > {t.name_en} ({t.name_ar}): {descriptions.get(t.doc_id, t.name_en)}"
        for t in tabs
    )
