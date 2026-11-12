"""Script-ratio language detection: fast, deterministic, no model needed for EN/AR."""

import re
from dataclasses import dataclass

from app.models.common import Lang

_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_LATIN = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class LanguageInfo:
    lang: Lang
    is_mixed: bool
    arabic_ratio: float


def detect_language(text: str, fallback: Lang = "en") -> LanguageInfo:
    ar = len(_ARABIC.findall(text))
    lat = len(_LATIN.findall(text))
    if ar + lat == 0:
        return LanguageInfo(fallback, False, 0.0)
    ratio = ar / (ar + lat)
    # Arabic sentences commonly embed English CRM terms ("CTS", "refund"); the request
    # language is whichever script dominates.
    lang: Lang = "ar" if ratio >= 0.5 else "en"
    return LanguageInfo(lang, 0.15 < ratio < 0.85, round(ratio, 3))


def script_of(text: str) -> Lang:
    """Which language a label is written in (Arabic if it contains any Arabic letter)."""
    return "ar" if _ARABIC.search(text) else "en"
