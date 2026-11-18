"""Chat memory nodes: record each answered turn, compact the history when it grows long.

Only `history` and `summary` survive between messages (via the LangGraph checkpointer, one
thread per session_id). Per the agreed design, refused/off-topic/error turns are NOT recorded -
only turns where generate_steps produced real content (state["answered"]).
Compaction runs AFTER the user already has their answer and fails OPEN: if the summarize call
fails, the history is simply kept as-is.
"""

import logging
from collections.abc import Callable

from app.config import Settings
from app.graph.state import ChatState

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
            summary = (getattr(reply, "content", None) or "").strip()
            if not summary:
                raise ValueError("empty summary")
        except Exception as exc:  # noqa: BLE001 - fail OPEN: compaction must never break a turn
            log.warning("history compaction failed, keeping full history: %s", exc)
            return {}
        log.info("history compacted: %d turns -> summary + %d", len(history), len(recent))
        return {"history": recent, "summary": summary}

    return compact_history
