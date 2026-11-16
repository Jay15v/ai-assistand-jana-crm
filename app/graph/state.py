"""Shared state that travels through the chatbot graph. Each node reads it and returns only the
fields it fills. Fields for later steps (scope decision, retrieved sections, chat history) will be
added here as their nodes are built.
"""

from typing import TypedDict

from app.models.chat import ChatRequest
from app.models.common import Lang
from app.models.menu import MenuResponse
from app.scope.tabs import Tab


class ChatState(TypedDict, total=False):
    # --- from the chat request ---
    message: str  # the user's question (used from step 2 on)
    ui_lang: Lang  # "en" / "ar": reply language
    menu: MenuResponse  # the user's menu JSON from the NestJS backend

    # --- step 1: resolve_tabs ---
    allowed_tabs: list[Tab]
    not_allowed_tabs: list[Tab]
    unknown_tabs: list[str]  # menu names with no vector DB tab (logged, skipped)
    error: str | None  # unusable menu (step 1) or a failed scope LLM call (step 2)

    # --- step 2: check_scope (LLM decision by meaning) ---
    scope: str  # "allowed" | "partial" | "not_allowed" | "off_topic"
    allowed_question: str | None  # partial only: the part the user may ask (answered in step 3)
    not_allowed_question: str | None  # partial only: the part outside their permissions
    scope_reason: str  # LLM's one-line reason, for logs only

    # --- output ---
    answer: str  # the text returned to the user


def initial_state(request: ChatRequest) -> ChatState:
    """The only way into the graph. The request is already validated by ChatRequest, so ui_lang
    is always "en" or "ar" (taken from the CRM switch, never guessed from the message text)."""
    return {"message": request.message, "ui_lang": request.ui_lang, "menu": request.menu}
