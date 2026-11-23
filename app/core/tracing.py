"""Admin-only chat tracing via Langfuse.

run_chat() is the one way to run a chat turn: it invokes the graph and, when
LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set, records the turn as one Langfuse trace
named "crm-chat" shaped per https://langfuse.com/docs/observability/best-practices:

* trace input = the user's message, trace output = the bot's answer (what the Sessions view
  shows, so a conversation reads like a chat thread); the full graph state and every LLM
  call's exact prompt/response stay on the nested spans for debugging
* user_id = employee_id (Users view), session_id -> Sessions view, env + lang tag
* the scope decision as a categorical "scope" score (filter all not_allowed/off_topic
  turns); user_name as trace metadata, display only

Without the keys the graph is invoked with the plain checkpointer config - no tracing code
runs, nothing else changes. End users never see any of this: traces live only in Langfuse,
behind the admin's login. Fails OPEN: a broken Langfuse setup must never break a chat turn.
"""

import logging
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.features.agent.schemas import ChatRequest
from app.features.agent.services.state import initial_state

log = logging.getLogger("crm_ai.tracing")

TRACE_NAME = "crm-chat"

_clients: list = []  # the Langfuse client(s) actually created, for flush() on shutdown


@lru_cache(maxsize=4)
def _make_tracer(public_key: str, secret_key: str, host: str, environment: str):
    """Create the Langfuse client + LangChain callback handler once per credential set.
    Construction is offline (events are batched to a background thread), so bad credentials
    surface as warnings in the Langfuse SDK logs, never as a failed chat turn."""
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        client = Langfuse(
            public_key=public_key, secret_key=secret_key, host=host, environment=environment
        )
        _clients.append(client)
        return client, CallbackHandler()
    except Exception as exc:  # noqa: BLE001 - fail OPEN
        log.warning("Langfuse tracing disabled (init failed): %s", exc)
        return None


def _get_tracer(settings: Settings):
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    return _make_tracer(
        settings.langfuse_public_key.get_secret_value(),
        settings.langfuse_secret_key.get_secret_value(),
        settings.langfuse_host,
        settings.langfuse_environment,
    )


def memory_key(request: ChatRequest) -> str:
    """The checkpointer thread of one chat: the user AND the session together, so a session id
    alone never opens someone else's conversation. The length prefix keeps the pair unambiguous
    (user "a" + session "b:c" can never equal user "a:b" + session "c")."""
    return f"{len(request.user_id)}:{request.user_id}:{request.session_id}"


def _run_graph(graph, request: ChatRequest, config: dict, progress: dict | None) -> dict:
    """Run the graph step by step and return its final state (what graph.invoke returns: invoke
    is this same loop inside LangGraph).

    After every step the full state so far is copied into `progress`, so when a step raises,
    the caller still holds everything the earlier steps produced.

    durability="exit": the chat memory is saved to the checkpointer once, when the turn ends
    (also when it ends in an error), instead of after every step. Nothing ever resumes a turn
    halfway, so the per-step saves were only extra database writes."""
    out: dict = {}
    for state in graph.stream(
        initial_state(request), config=config, stream_mode="values", durability="exit"
    ):
        out = state
        if progress is not None:
            progress.clear()
            progress.update(state)
    return out


def run_chat(
    graph, request: ChatRequest, settings: Settings | None = None, progress: dict | None = None
) -> dict:
    """Run one chat turn through the graph, traced when Langfuse is configured.

    `progress` (optional, one fresh dict per turn) is kept up to date with the turn's state
    after each step; it is how a turn that crashes halfway can still be logged."""
    settings = settings or get_settings()
    config: dict = {"configurable": {"thread_id": memory_key(request)}}
    tracer = _get_tracer(settings)
    if tracer is None:
        return _run_graph(graph, request, config, progress)

    client, handler = tracer
    from langfuse import propagate_attributes

    with propagate_attributes(
        trace_name=TRACE_NAME,
        user_id=request.user_id,  # employee_id: stable UUID -> Langfuse Users view
        session_id=request.session_id,  # -> Langfuse Sessions view (chat thread)
        tags=[f"lang:{request.ui_lang}"],
        metadata={"user_name": request.user_name} if request.user_name else None,
    ):
        # Our own root span so the TRACE input/output (derived from the root observation) are
        # the readable message/answer pair per the best-practices docs, while the nested
        # LangGraph span keeps the full state for debugging.
        with client.start_as_current_observation(
            name=TRACE_NAME, as_type="span", input=request.message
        ) as span:
            out = _run_graph(graph, request, {**config, "callbacks": [handler]}, progress)
            span.update(output=out.get("answer") or "")
            try:
                # Post-hoc label (docs: use scores, not tags, for labels known after the run).
                client.score_current_trace(
                    name="scope", value=out.get("scope") or "error", data_type="CATEGORICAL"
                )
            except Exception as exc:  # noqa: BLE001 - fail OPEN
                log.warning("Langfuse scope score failed: %s", exc)
    return out


def flush() -> None:
    """Send any queued trace events now. Call on process shutdown so the last turns aren't lost."""
    for client in _clients:
        try:
            client.flush()
        except Exception:  # noqa: BLE001 - shutdown must not fail over tracing
            pass
