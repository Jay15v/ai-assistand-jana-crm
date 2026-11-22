"""Data shapes of the agent feature: the NestJS menu, the chat request, and the crawled CRM documents."""

from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.locale import Lang, parse_ui_lang
from app.core.normalize import normalize_text

# --------------------------------------------------------------------------------------------------
# Menu
#
# Contract for the per-user menu JSON that the NestJS backend sends with every chat request.
#
# Only `result[].menuitems[].name` drives the scope logic. `privileges`, `href` and the ids are
# parsed but unused for now (privileges are a possible second-level check later). Unknown extra
# fields are ignored so a backend change does not break parsing.
# --------------------------------------------------------------------------------------------------


class MenuPrivilege(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    status: int


class MenuItem(BaseModel):
    """One sidebar tab the user is allowed to open."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    href: str | None = None
    privileges: list[MenuPrivilege] = []


class MenuGroup(BaseModel):
    """One sidebar menu (e.g. 'Tickets') with its tabs."""

    model_config = ConfigDict(extra="ignore")

    menuName: str
    id: int
    menuitems: list[MenuItem] = []


class MenuResponse(BaseModel):
    """The full response of the NestJS menu endpoint."""

    model_config = ConfigDict(extra="ignore")

    result: list[MenuGroup] = []
    success: bool = True
    is_maintenance: bool = False

    def tab_names(self) -> list[str]:
        """All tab names in menu order, duplicates removed (first occurrence wins)."""
        seen: dict[str, None] = {}
        for group in self.result:
            for item in group.menuitems:
                if item.name not in seen:
                    seen[item.name] = None
        return list(seen)


# --------------------------------------------------------------------------------------------------
# Chat request
#
# Contract for one chat message sent to the AI service by the CRM (frontend, or NestJS forwarding it).
# --------------------------------------------------------------------------------------------------


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    # Optional display name (e.g. the CRM user_name) shown next to the user in the admin
    # tracing UI. Not used anywhere in the pipeline itself.
    user_name: str | None = None
    message: str = Field(min_length=1, max_length=2000)
    # Current value of the CRM's EN / Arabic switch at the moment the message is sent.
    # Decides the reply language AND which label (en/ar) is used for tab names.
    # Required: a missing or unknown value is rejected (HTTP 422) instead of silently guessed.
    ui_lang: Lang
    # The user's menu JSON from the NestJS backend (get-role-privileges), sent with every message.
    # Decides which CRM tabs the user is allowed to ask about.
    menu: MenuResponse

    @field_validator("ui_lang", mode="before")
    @classmethod
    def _normalize_ui_lang(cls, v: object) -> Lang:
        lang = parse_ui_lang(v) if isinstance(v, str) else None
        if lang is None:
            raise ValueError("ui_lang must be 'en' or 'ar' (locale forms such as 'ar-EG' or 'en_US' are accepted)")
        return lang


class ScopeRequest(BaseModel):
    """Body of POST /agent/scope: only what the scope decision needs."""

    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=2000)
    menu: MenuResponse


class ChatResponse(BaseModel):
    """What POST /chat returns. Nothing else from the graph state leaves the service."""

    session_id: str
    answer: str  # the text shown to the user, already in the ui_lang of the request
    scope: Literal["allowed", "partial", "not_allowed", "off_topic", "error"]


# --------------------------------------------------------------------------------------------------
# CRM documents
#
# Schema of the crawled CRM knowledge documents and the keys used to match them to a user.
#
# Source: data/vector_docs/ability_crm_vector_docs.json. Labels are taken as crawled;
# a missing Arabic label stays null (never machine-translated or invented).
#
# Matching keys (for the future per-user tab cache from NestJS):
#   * href      - URL path without host and locale, e.g. "/definitions/department".
#                 This is the strongest key: the NestJS menu item carries the same href.
#   * names     - normalized EN + AR group / screen / path labels, the fallback key.
# --------------------------------------------------------------------------------------------------

DocType = Literal["group", "screen", "tab", "form", "detail_view"]
_LOCALES = {"en", "ar"}


class Label(BaseModel):
    """A user-facing label. Arabic may be missing in the crawl (null)."""

    model_config = ConfigDict(extra="allow")  # keeps extras such as "required"

    en: str | None = None
    ar: str | None = None


class CrmDoc(BaseModel):
    model_config = ConfigDict(extra="allow")  # tabs, columns, actions, form_fields, ...

    id: str
    type: DocType
    group: Label
    screen: Label
    path: Label
    url: str | None = None
    parent: str | None = None
    navigation_steps: list[Label] = []
    text_en: str
    text_ar: str

    @property
    def href(self) -> str | None:
        return href_from_url(self.url)

    def missing_ar_labels(self) -> int:
        """How many labels have English but no Arabic (data-quality signal)."""
        return _count_missing_ar(self.model_dump())


def href_from_url(url: str | None) -> str | None:
    """'https://host/en/definitions/department' -> '/definitions/department'."""
    if not url:
        return None
    parts = [p for p in urlparse(url).path.split("/") if p]
    if parts and parts[0] in _LOCALES:
        parts = parts[1:]
    return "/" + "/".join(parts) if parts else "/"


def _count_missing_ar(obj: Any) -> int:
    if isinstance(obj, dict):
        own = 1 if obj.get("en") and "ar" in obj and not obj.get("ar") else 0
        return own + sum(_count_missing_ar(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(_count_missing_ar(v) for v in obj)
    return 0


def _labels(items: Any, lang: str) -> list[str]:
    if not isinstance(items, list):
        return []
    return [i[lang] for i in items if isinstance(i, dict) and i.get(lang)]


def title_text(doc: CrmDoc, lang: str) -> str:
    """Short intent-focused text: what the screen is and what you can do there.
    Long column/filter lists are left to the full-text record so they don't dilute this one."""
    extra = doc.model_extra or {}
    name = getattr(doc.screen, lang) or doc.screen.en
    path = getattr(doc.path, lang) or doc.path.en
    parts = [name, path]
    tab = extra.get("tab")
    if isinstance(tab, dict) and tab.get(lang):
        parts.append(tab[lang])
    actions = _labels(extra.get("actions"), lang)
    tabs = _labels(extra.get("tabs"), lang)
    screens = _labels(extra.get("screens"), lang)
    if actions:
        parts.append(", ".join(actions))
    if tabs:
        parts.append(", ".join(tabs))
    if screens:
        parts.append(", ".join(screens))
    return " | ".join(p for p in parts if p)


def record_metadata(doc: CrmDoc, lang: str, kind: str) -> dict[str, str | int | bool]:
    """Flat Chroma metadata for one record of a document (no None values allowed)."""
    return {
        "doc_id": doc.id,
        "lang": lang,
        "kind": kind,  # "title" (short intent text) or "full" (whole page text)
        "type": doc.type,
        "parent": doc.parent or "",
        "href": doc.href or "",
        "group_en": doc.group.en or "",
        "group_ar": doc.group.ar or "",
        "screen_en": doc.screen.en or "",
        "screen_ar": doc.screen.ar or "",
        "path_en": doc.path.en or "",
        "path_ar": doc.path.ar or "",
        "norm_group_en": normalize_text(doc.group.en or ""),
        "norm_group_ar": normalize_text(doc.group.ar or ""),
        "norm_screen_en": normalize_text(doc.screen.en or ""),
        "norm_screen_ar": normalize_text(doc.screen.ar or ""),
        "missing_ar": doc.missing_ar_labels(),
        "doc_json": doc.model_dump_json(),
    }
