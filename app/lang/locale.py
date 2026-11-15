"""Reply language = the language the user picked in the CRM's "EN - English / ع - Arabic" switch.

The CRM frontend sends its current UI locale with every chat message (`ui_lang`). The message
text is NOT used to guess the language: a question typed in Arabic while the CRM is in English
is answered in English, so the tab names in the answer match what is on the user's screen.
"""

from app.models.common import Lang

SUPPORTED_LANGS: tuple[Lang, ...] = ("en", "ar")


def parse_ui_lang(value: str | None) -> Lang | None:
    """Normalize a locale value from the frontend to "en" / "ar".

    Accepts the forms a frontend commonly sends: "en", "AR", "ar-EG", "en_US", " ar ".
    Returns None for anything else (missing, empty, or an unsupported language).
    """
    if not value or not isinstance(value, str):
        return None
    code = value.strip().lower().replace("_", "-").split("-", 1)[0]
    return code if code in SUPPORTED_LANGS else None  # type: ignore[return-value]
