"""Deterministic Arabic/English text normalization used for matching and sparse search."""

import re
import unicodedata

_AR_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
_TATWEEL = "ـ"
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)

_CHAR_MAP = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
        "_": " ",
        **{chr(0x0660 + i): str(i) for i in range(10)},  # Arabic-Indic digits
        **{chr(0x06F0 + i): str(i) for i in range(10)},  # Extended Arabic-Indic digits
    }
)

STOPWORDS = frozenset(
    {
        # English
        "a", "an", "the", "how", "do", "does", "did", "i", "can", "could", "to", "in",
        "on", "of", "for", "my", "is", "are", "what", "where", "which", "me", "you",
        "please", "and", "or", "with", "this", "that", "it", "from", "at", "by", "be",
        "should", "need", "want", "would", "use", "using", "there", "way", "screen",
        # Arabic (already normalized form)
        "كيف", "ازاي", "اين", "فين", "ما", "ماذا", "هل", "من", "في", "على", "علي", "الى",
        "الي", "عن", "مع", "او", "و", "انا", "اريد", "عايز", "عاوز", "ممكن", "لو", "يا",
        "هذا", "هذه", "ذلك", "التي", "الذي", "طريقه", "اعمل", "اقدر", "يمكنني",
    }
)


def normalize_text(text: str) -> str:
    """Lower-case, unify Arabic letter variants, strip diacritics/punctuation, collapse spaces."""
    t = unicodedata.normalize("NFKC", text)
    t = _AR_DIACRITICS.sub("", t).replace(_TATWEEL, "")
    t = t.translate(_CHAR_MAP).lower()
    t = _NON_WORD.sub(" ", t)
    return " ".join(t.split())


def _light_stems(token: str) -> list[str]:
    out = [token]
    if token.startswith("وال") and len(token) > 5:
        out.append(token[3:])
    elif token.startswith("ال") and len(token) > 4:
        out.append(token[2:])
    elif token.startswith("لل") and len(token) > 4:
        out.append(token[2:])
    if token.isascii():
        if token.endswith("ies") and len(token) > 4:
            out.append(token[:-3] + "y")
        elif token.endswith("s") and not token.endswith("ss") and len(token) > 3:
            out.append(token[:-1])
    return out


def search_tokens(text: str) -> list[str]:
    """Normalized tokens with stopwords removed and light stem variants added."""
    tokens: list[str] = []
    for tok in normalize_text(text).split():
        if tok in STOPWORDS or len(tok) < 2:
            continue
        tokens.extend(_light_stems(tok))
    return tokens
