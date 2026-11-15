"""Step 1 of the scope flow: which CRM tabs is this user allowed to use?

Input : the per-user menu JSON from the NestJS backend (sent with every chat request).
Output: the vector DB's 54 tabs split into `allowed` (present in the user's menu) and
        `not_allowed` (everything else). Step 2 (the LLM scope decision) consumes both lists.

Matching is static and exact (normalized tab name == normalized screen name); the user's
QUESTION is never matched here. Four endpoint names differ from the crawled screen names and
are bridged by TAB_ALIASES.
"""

import logging
from dataclasses import dataclass

from app.config import Settings
from app.lang.normalize import normalize_text
from app.models.menu import MenuResponse
from app.vectordb.schema import CrmDoc
from app.vectordb.store import load_docs

log = logging.getLogger("crm_ai.scope")

# Endpoint tab name -> screen name in the vector DB (the crawl stored the menu name for these).
TAB_ALIASES: dict[str, str] = {
    "Search Unit": "Unit",
    "Document Library": "DocumentLibrary",
    "System Settings": "Settings",
    "Send Notifications": "Notifications",
}
_NORM_ALIASES = {normalize_text(k): normalize_text(v) for k, v in TAB_ALIASES.items()}


class MenuUnavailableError(RuntimeError):
    """The menu response cannot be trusted (failed or in maintenance) - do not treat the
    user as having no tabs; the caller should surface an error instead."""


@dataclass(frozen=True)
class Tab:
    """One CRM screen/tab as known by the vector DB, with both display names."""

    doc_id: str
    name_en: str
    name_ar: str
    menu_en: str
    menu_ar: str


@dataclass(frozen=True)
class UserTabs:
    allowed: list[Tab]
    not_allowed: list[Tab]
    unknown_names: list[str]  # endpoint names with no vector DB tab (new tabs; logged, skipped)


class TabCatalog:
    """The 54 `screen` documents of the vector DB, indexed by normalized English name."""

    def __init__(self, docs: list[CrmDoc]):
        self.tabs: list[Tab] = []
        self._by_norm_name: dict[str, Tab] = {}
        for d in docs:
            if d.type != "screen":
                continue
            tab = Tab(
                doc_id=d.id,
                name_en=d.screen.en or "",
                name_ar=d.screen.ar or d.screen.en or "",
                menu_en=d.group.en or "",
                menu_ar=d.group.ar or d.group.en or "",
            )
            key = normalize_text(tab.name_en)
            if key in self._by_norm_name:
                raise ValueError(f"duplicate tab name in vector DB: {tab.name_en!r}")
            self.tabs.append(tab)
            self._by_norm_name[key] = tab

    @classmethod
    def from_settings(cls, settings: Settings) -> "TabCatalog":
        return cls(load_docs(settings.vector_docs_path))

    def find(self, endpoint_name: str) -> Tab | None:
        key = normalize_text(endpoint_name)
        return self._by_norm_name.get(_NORM_ALIASES.get(key, key))


def resolve_user_tabs(menu: MenuResponse, catalog: TabCatalog) -> UserTabs:
    """Split the catalog into the user's allowed / not-allowed tabs by exact name matching."""
    if not menu.success:
        raise MenuUnavailableError("menu response has success=false")
    if menu.is_maintenance:
        raise MenuUnavailableError("backend is in maintenance mode")

    allowed_ids: set[str] = set()
    unknown: list[str] = []
    for name in menu.tab_names():
        tab = catalog.find(name)
        if tab is None:
            log.warning("menu tab %r has no match in the vector DB - skipped", name)
            unknown.append(name)
        else:
            allowed_ids.add(tab.doc_id)

    allowed = [t for t in catalog.tabs if t.doc_id in allowed_ids]
    not_allowed = [t for t in catalog.tabs if t.doc_id not in allowed_ids]
    log.info(
        "user tabs resolved: %d allowed, %d not allowed, %d unknown",
        len(allowed), len(not_allowed), len(unknown),
    )
    return UserTabs(allowed=allowed, not_allowed=not_allowed, unknown_names=unknown)
