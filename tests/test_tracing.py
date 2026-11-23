"""run_chat: Langfuse tracing is opt-in via keys and must never affect the graph invocation
when off. No network in any test: client/handler construction and span creation are offline
(events batch in a background thread that only ships when credentials are real)."""

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.tracing import TRACE_NAME, _make_tracer, run_chat
from app.features.agent.schemas import ChatRequest

FIXTURES = Path(__file__).parent / "fixtures"
THREAD = "36:749dcb00-aaaa-bbbb-cccc-000000000001:sess-42"  # memory_key: user + session


@pytest.fixture(autouse=True)
def fresh_tracer_cache():
    _make_tracer.cache_clear()
    yield
    _make_tracer.cache_clear()


class FakeGraph:
    """Records the (state, config) of each run and yields the state after each "step": first
    as received, then answered (run_chat streams the graph and returns the last state)."""

    def __init__(self):
        self.calls: list = []

    def stream(self, state, config=None, stream_mode=None, durability=None):
        assert stream_mode == "values"
        assert durability == "exit"  # chat memory is saved once per turn, not after every step
        self.calls.append((state, config))
        yield dict(state)
        yield {**state, "answer": "THE ANSWER", "scope": "allowed"}


def request() -> ChatRequest:
    menu = json.loads((FIXTURES / "menu_admin.json").read_text(encoding="utf-8"))
    return ChatRequest(
        user_id="749dcb00-aaaa-bbbb-cccc-000000000001",
        user_name="superAdmin",
        session_id="sess-42",
        message="how do I add a ticket?",
        ui_lang="en",
        menu=menu,
    )


def settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_no_keys_means_plain_invoke():
    graph = FakeGraph()
    out = run_chat(graph, request(), settings())
    assert out["answer"] == "THE ANSWER"
    state, config = graph.calls[0]
    assert state["message"] == "how do I add a ticket?"
    assert config == {"configurable": {"thread_id": THREAD}}


def test_progress_follows_the_turn_step_by_step():
    """The caller's dict holds the latest state, so a crash keeps what earlier steps produced."""

    class CrashesAfterScope:
        def stream(self, state, config=None, **kwargs):
            yield dict(state)
            yield {**state, "standalone_question": "How do I add a ticket?"}
            raise RuntimeError("search crashed")

    progress: dict = {"left over": "from nowhere"}
    with pytest.raises(RuntimeError):
        run_chat(CrashesAfterScope(), request(), settings(), progress)
    assert progress["standalone_question"] == "How do I add a ticket?"
    assert progress["message"] == "how do I add a ticket?"
    assert "left over" not in progress

    done: dict = {}
    out = run_chat(FakeGraph(), request(), settings(), done)
    assert done == out


def test_one_key_alone_is_not_enough():
    graph = FakeGraph()
    run_chat(graph, request(), settings(langfuse_public_key="pk-lf-x"))
    _, config = graph.calls[0]
    assert "callbacks" not in config


def test_keys_turn_on_the_callback_and_keep_the_thread():
    graph = FakeGraph()
    s = settings(langfuse_public_key="pk-lf-x", langfuse_secret_key="sk-lf-x")
    run_chat(graph, request(), s)
    _, config = graph.calls[0]
    assert config["configurable"] == {"thread_id": THREAD}
    assert len(config["callbacks"]) == 1


def test_identity_reaches_the_trace_attributes(monkeypatch):
    """user_id / session_id / tags must go through propagate_attributes."""
    import langfuse

    captured = {}

    class FakePropagate:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(langfuse, "propagate_attributes", FakePropagate)
    s = settings(langfuse_public_key="pk-lf-x", langfuse_secret_key="sk-lf-x")
    run_chat(FakeGraph(), request(), s)
    assert captured["trace_name"] == TRACE_NAME
    assert captured["user_id"] == "749dcb00-aaaa-bbbb-cccc-000000000001"
    assert captured["session_id"] == "sess-42"
    assert captured["tags"] == ["lang:en"]


def test_tracer_is_reused_across_turns():
    graph = FakeGraph()
    s = settings(langfuse_public_key="pk-lf-x", langfuse_secret_key="sk-lf-x")
    run_chat(graph, request(), s)
    run_chat(graph, request(), s)
    first, second = graph.calls[0][1]["callbacks"][0], graph.calls[1][1]["callbacks"][0]
    assert first is second


def test_tracer_init_failure_falls_back_to_plain_invoke(monkeypatch):
    import app.core.tracing as tracing

    monkeypatch.setattr(tracing, "_make_tracer", lambda *a: None)
    graph = FakeGraph()
    s = settings(langfuse_public_key="pk-lf-x", langfuse_secret_key="sk-lf-x")
    out = run_chat(graph, request(), s)
    assert out["answer"] == "THE ANSWER"
    assert graph.calls[0][1] == {"configurable": {"thread_id": THREAD}}
