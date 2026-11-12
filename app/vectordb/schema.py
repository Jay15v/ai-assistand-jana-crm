"""Schema of the crawled CRM knowledge documents and the keys used to match them to a user.

Source: app/data/vector_docs/ability_crm_vector_docs.json. Labels are taken as crawled;
a missing Arabic label stays null (never machine-translated or invented).

Matching keys (for the future per-user tab cache from NestJS):
  * href      - URL path without host and locale, e.g. "/definitions/department".
                This is the strongest key: the NestJS menu item carries the same href.
  * names     - normalized EN + AR group / screen / path labels, the fallback key.
"""

from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from app.lang.normalize import normalize_text

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
