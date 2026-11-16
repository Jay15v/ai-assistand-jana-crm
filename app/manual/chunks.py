"""Parse the EN + AR user manuals into answer chunks (one per ### question).

Each chunk carries the English section text, its Arabic twin's text (when the AR manual has one),
and the tags from app/data/manual/section_tabs(.ar).json. Image lines are stripped - screenshots
are internal reference material and never reach the index or the user.
"""

import json
import re
from pathlib import Path

from pydantic import BaseModel

from app.config import ROOT_DIR

EN_MANUAL = ROOT_DIR / "Ability_CRM_User_Manual.md"
AR_MANUAL = ROOT_DIR / "Ability_CRM_User_Manual_AR.md"
EN_TAGS = ROOT_DIR / "app" / "data" / "manual" / "section_tabs.json"
AR_TAGS = ROOT_DIR / "app" / "data" / "manual" / "section_tabs_ar.json"

_IMAGE_LINE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")
_INLINE_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


class ManualChunk(BaseModel):
    id: str  # stable within one build, e.g. "manual.0291" (EN manual line of the ### heading)
    section_en: str  # the ## menu header, e.g. "12. Invoices"
    question_en: str
    question_ar: str | None  # None for the 2 EN questions with no Arabic twin
    text_en: str  # "### question\n" + body, images stripped
    text_ar: str | None
    tabs: list[str]  # English tab names (step 1's vocabulary); [] for general
    require: str  # "any" | "all"
    general: bool

    def title_text(self) -> str:
        """The bilingual record embedded for intent matching (option C)."""
        return f"{self.question_en} | {self.question_ar}" if self.question_ar else self.question_en

    def text(self, lang: str) -> str:
        """The answer source for a reply language; EN is the fallback (confirmed behavior)."""
        return self.text_ar if lang == "ar" and self.text_ar else self.text_en


def _strip_images(body: str) -> str:
    lines = [ln for ln in body.splitlines() if not _IMAGE_LINE.match(ln)]
    return _INLINE_IMAGE.sub("", "\n".join(lines)).strip()


def _section_bodies(path: Path) -> dict[str, tuple[int, str]]:
    """{### question: (line number, stripped body text)} for one manual file."""
    out: dict[str, tuple[int, str]] = {}
    current: tuple[str, int] | None = None
    buf: list[str] = []

    def flush() -> None:
        if current:
            q, n = current
            out[q] = (n, _strip_images("\n".join(buf)))

    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## ") or line.startswith("### "):
            flush()
            current = (line[4:].strip(), n) if line.startswith("### ") else None
            buf = []
        elif current:
            buf.append(line)
    flush()
    return out


def load_chunks() -> list[ManualChunk]:
    en_rows = json.loads(EN_TAGS.read_text(encoding="utf-8"))
    ar_by_en = {r["en_question"]: r for r in json.loads(AR_TAGS.read_text(encoding="utf-8"))}
    en_bodies = _section_bodies(EN_MANUAL)
    ar_bodies = _section_bodies(AR_MANUAL)

    chunks: list[ManualChunk] = []
    for row in en_rows:
        q = row["question"]
        line, body = en_bodies[q]
        ar_row = ar_by_en.get(q)
        ar_q = ar_row["question"] if ar_row else None
        chunks.append(ManualChunk(
            id=f"manual.{line:04d}",
            section_en=row["section"],
            question_en=q,
            question_ar=ar_q,
            text_en=f"### {q}\n{body}",
            text_ar=f"### {ar_q}\n{ar_bodies[ar_q][1]}" if ar_q and ar_q in ar_bodies else None,
            tabs=row["tabs"],
            require=row.get("require", "any"),
            general=row["general"],
        ))
    return chunks
