"""The state that travels through the chatbot graph, and the chat memory kept inside it."""

import logging
from collections.abc import Callable
from typing import TypedDict

from app.core.config import Settings
from app.core.llm import reply_text
from app.core.locale import Lang
from app.features.agent.repositories.tabs import Tab
from app.features.agent.schemas import ChatRequest, MenuResponse

# --------------------------------------------------------------------------------------------------
# State
#
# Shared state that travels through the chatbot graph. Each node reads it and returns only the
# fields it fills. Fields for later steps (scope decision, retrieved sections, chat history) will be
# added here as their nodes are built.
# --------------------------------------------------------------------------------------------------

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


# --------------------------------------------------------------------------------------------------
# History
#
# Chat memory nodes: record each answered turn, compact the history when it grows long.
#
# Only `history` and `summary` survive between messages (via the LangGraph checkpointer, one
# thread per session_id). Per the agreed design, refused/off-topic/error turns are NOT recorded -
# only turns where generate_steps produced real content (state["answered"]).
# Compaction runs AFTER the user already has their answer and fails OPEN: if the summarize call
# fails, the history is simply kept as-is.
# --------------------------------------------------------------------------------------------------

log = logging.getLogger("crm_ai.history")

SUMMARIZE_PROMPT = (
    "Summarize this CRM support conversation in ONE short paragraph (max 80 words), keeping "
    "what matters for follow-up questions: which screens/records were discussed and what the "
    "user was shown how to do. Merge with the previous summary if one is given. Reply with the "
    "summary only, in English.\n\nPrevious summary: {summary}\n\nTurns to fold in:\n{turns}"
)


def history_text(state: ChatState, max_answer_chars: int = 400) -> str:
    """The conversation context handed to the LLM prompts: summary + recent turns verbatim."""
    parts = []
    if state.get("summary"):
        parts.append(f"(summary of earlier conversation: {state['summary']})")
    for turn in state.get("history") or []:
        answer = turn["assistant"]
        if len(answer) > max_answer_chars:
            answer = answer[:max_answer_chars] + " ..."
        parts.append(f"User: {turn['user']}\nAssistant: {answer}")
    return "\n\n".join(parts)


def record_turn(state: ChatState) -> dict:
    """Append this exchange to the session history - only when a real answer was produced."""
    if not state.get("answered"):
        return {}
    history = list(state.get("history") or [])
    history.append({"user": state["message"], "assistant": state["answer"]})
    return {"history": history}


def make_compact_history(get_llm: Callable[[], object], settings: Settings) -> Callable[[ChatState], dict]:
    cache: list = []

    def compact_history(state: ChatState) -> dict:
        history = state.get("history") or []
        if len(history) <= settings.compact_after_turns:
            return {}
        keep = settings.history_keep_turns
        old, recent = history[:-keep], history[-keep:]
        turns = "\n".join(f"User: {t['user']}\nAssistant: {t['assistant']}" for t in old)
        prompt = SUMMARIZE_PROMPT.format(summary=state.get("summary") or "(none)", turns=turns)
        try:
            if not cache:
                cache.append(get_llm())
            reply = cache[0].invoke([("human", prompt)])
            summary = reply_text(reply)
            if not summary:
                raise ValueError("empty summary")
        except Exception as exc:  # noqa: BLE001 - fail OPEN: compaction must never break a turn
            log.warning("history compaction failed, keeping full history: %s", exc)
            return {}
        log.info("history compacted: %d turns -> summary + %d", len(history), len(recent))
        return {"history": recent, "summary": summary}

    return compact_history
