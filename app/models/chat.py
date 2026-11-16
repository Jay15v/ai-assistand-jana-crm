"""Contract for one chat message sent to the AI service by the CRM (frontend, or NestJS forwarding it)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.lang.locale import parse_ui_lang
from app.models.common import Lang
from app.models.menu import MenuResponse


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
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
