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

    # --- chat memory (the ONLY fields that survive between messages of a session) ---
    history: list  # recent turns verbatim: [{"user": ..., "assistant": ...}]
    summary: str  # one paragraph summarizing older, compacted-away turns

    # --- step 2: check_scope (LLM decision by meaning) ---
    scope: str  # "allowed" | "partial" | "not_allowed" | "off_topic"
    standalone_question: str | None  # the message rewritten self-contained ("edit it" -> "edit a ticket")
    allowed_question: str | None  # partial only: the part the user may ask (answered in step 3)
    not_allowed_question: str | None  # partial only: the part outside their permissions
    scope_reason: str  # LLM's one-line reason, for logs only
    answered: bool  # True only when generate_steps produced real content (controls record_turn)

    # --- step 3: retrieve_section ---
    sections: list  # list[ManualChunk]: the eligible manual sections for this question

    # --- output ---
    answer: str  # the text returned to the user


def initial_state(request: ChatRequest) -> ChatState:
    """The only way into the graph. The request is already validated by ChatRequest, so ui_lang
    is always "en" or "ar" (taken from the CRM switch, never guessed from the message text).

    With a checkpointer, the state persists per session - so every PER-MESSAGE field is reset
    here explicitly, or last turn's scope/answer/error would leak into this turn. Only `history`
    and `summary` are left out: they are the session's memory. The menu is always taken fresh
    from the request, so permission changes apply mid-session.
    """
    return {
        "message": request.message,
        "ui_lang": request.ui_lang,
        "menu": request.menu,
        # transient resets:
        "allowed_tabs": [],
        "not_allowed_tabs": [],
        "unknown_tabs": [],
        "error": None,
        "scope": "",
        "standalone_question": None,
        "allowed_question": None,
        "not_allowed_question": None,
        "scope_reason": "",
        "answered": False,
        "sections": [],
        "answer": "",
    }
