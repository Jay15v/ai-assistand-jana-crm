"""Runs one chat turn for a session and shapes what goes back to the caller."""

from app.core.config import Settings
from app.core.tracing import run_chat
from app.features.agent.schemas import ChatRequest, ChatResponse


class ChatService:
    def __init__(self, graph, settings: Settings):
        self.graph = graph
        self.settings = settings

    def send(self, request: ChatRequest) -> ChatResponse:
        """One message in, one reply out. The session's memory is keyed by request.session_id."""
        out = run_chat(self.graph, request, self.settings)
        return ChatResponse(
            session_id=request.session_id,
            answer=out.get("answer") or "",
            scope=out.get("scope") or "error",  # no scope = the turn failed before the decision
        )
