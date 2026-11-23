"""Runs one chat turn for a session, logs it to the history tables, and shapes the reply."""

import logging
import time

from app.core.config import Settings
from app.core.tracing import run_chat
from app.features.agent.schemas import ChatRequest, ChatResponse
from app.features.conversation.repositories.history import (
    BackgroundHistoryWriter,
    ChatHistoryRepository,
    Turn,
)

log = logging.getLogger("crm_ai.chat")


class ChatService:
    def __init__(
        self,
        graph,
        settings: Settings,
        history: ChatHistoryRepository | BackgroundHistoryWriter | None = None,
    ):
        self.graph = graph
        self.settings = settings
        # None = no DATABASE_URL: nothing is logged. The app passes the background writer, so
        # a reply never waits for the history write.
        self.history = history

    def send(self, request: ChatRequest) -> ChatResponse:
        """One message in, one reply out."""
        out = self.run(request)
        return ChatResponse(
            session_id=request.session_id,
            answer=out.get("answer") or "",
            scope=out.get("scope") or "error",  # no scope = the turn failed before the decision
        )

    def run(self, request: ChatRequest) -> dict:
        """Run the turn and log it. Returns the graph's full output (scripts print more of it).

        A turn that crashes is still logged before the exception goes on: as scope "error",
        with whatever the steps that did finish produced (e.g. the standalone question)."""
        started = time.perf_counter()
        progress: dict = {}  # this turn's state after each finished step; never shared
        try:
            out = run_chat(self.graph, request, self.settings, progress)
        except Exception:
            self._log(request, progress, started, crashed=True)
            raise
        self._log(request, out, started)
        return out

    def _log(self, request: ChatRequest, out: dict, started: float, crashed: bool = False) -> None:
        """Fail open: a database problem is logged, never shown to the user.

        `crashed`: the turn raised halfway, so `out` is partial. The row is marked scope "error"
        (the table's only crash marker); the fields already produced are kept, the rest empty."""
        if self.history is None:
            return
        try:
            self.history.log_turn(Turn(
                user_id=request.user_id,
                session_id=request.session_id,
                user_name=request.user_name,
                user_message=request.message,
                standalone_question=out.get("standalone_question"),
                answer=out.get("answer") or "",
                scope="error" if crashed else (out.get("scope") or "error"),
                scope_reason=out.get("scope_reason") or None,
                ui_lang=request.ui_lang,
                latency_ms=round((time.perf_counter() - started) * 1000),
            ))
        except Exception:  # noqa: BLE001 - fail OPEN
            log.exception("chat history write failed (session %s)", request.session_id)
