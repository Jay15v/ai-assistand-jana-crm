"""Reply language comes from the CRM's EN / Arabic switch (ui_lang), never from the message text."""

import pytest
from pydantic import ValidationError

from app.lang.locale import parse_ui_lang
from app.models.chat import ChatRequest


@pytest.mark.parametrize(
    "value, expected",
    [
        ("en", "en"),
        ("ar", "ar"),
        ("EN", "en"),
        ("AR", "ar"),
        (" ar ", "ar"),
        ("ar-EG", "ar"),
        ("ar_EG", "ar"),
        ("en-US", "en"),
    ],
)
def test_locale_forms_are_normalized(value, expected):
    assert parse_ui_lang(value) == expected


@pytest.mark.parametrize("value", [None, "", "   ", "fr", "arabic", "english", "e", "-ar"])
def test_unsupported_or_missing_locale_is_none(value):
    assert parse_ui_lang(value) is None


def _req(**overrides):
    data = {"user_id": "u1", "session_id": "s1", "message": "how do I add a department", "ui_lang": "en"}
    data.update(overrides)
    return ChatRequest(**data)


def test_chat_request_normalizes_ui_lang():
    assert _req(ui_lang="ar-EG").ui_lang == "ar"


@pytest.mark.parametrize(
    "message, ui_lang",
    [
        ("ازاي اعمل استرداد للفاتورة", "en"),  # Arabic text, CRM in English -> English reply
        ("How do I refund an invoice?", "ar"),  # English text, CRM in Arabic -> Arabic reply
        ("ezay a3mel refund", "ar"),  # Arabizi: the text plays no role either way
    ],
)
def test_reply_language_follows_switch_not_text(message, ui_lang):
    assert _req(message=message, ui_lang=ui_lang).ui_lang == ui_lang


@pytest.mark.parametrize("bad", ["fr", "", "arabic"])
def test_chat_request_rejects_unknown_ui_lang(bad):
    with pytest.raises(ValidationError):
        _req(ui_lang=bad)


def test_chat_request_requires_ui_lang():
    data = {"user_id": "u1", "session_id": "s1", "message": "hi"}
    with pytest.raises(ValidationError):
        ChatRequest(**data)


def test_chat_request_rejects_blank_message():
    with pytest.raises(ValidationError):
        _req(message="   ")
