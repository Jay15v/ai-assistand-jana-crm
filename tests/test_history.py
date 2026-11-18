"""Chat memory: checkpointer sessions, follow-ups, recording rules, compaction (fake LLM)."""

import json
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.config import get_settings
from app.graph.build import build_graph
from app.graph.history import make_compact_history, record_turn
from app.graph.state import initial_state
from app.manual.chunks import load_chunks
from app.models.chat import ChatRequest
from app.scope.decide import ScopeDecision
from app.scope.tabs import TabCatalog
from tests.conftest import FakeIndex, FakeLLM

FIXTURES = Path(__file__).parent / "fixtures"
MENU = json.loads((FIXTURES / "menu_readonly_role.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def catalog():
    return TabCatalog.from_settings(get_settings())


@pytest.fixture(scope="module")
def ticket_chunk():
    return next(c for c in load_chunks() if c.question_en == "How do I search for tickets?")


def make_graph(catalog, fake, chunk):
    return build_graph(catalog, llm=fake, index=FakeIndex(hits=[(chunk, 0.9)]),
                       checkpointer=InMemorySaver())


def send(graph, message, session="s1", ui_lang="en"):
    req = ChatRequest(user_id="u1", session_id=session, message=message, ui_lang=ui_lang, menu=MENU)
    return graph.invoke(initial_state(req), config={"configurable": {"thread_id": session}})


def allowed_fake(**kw):
    return FakeLLM(ScopeDecision(decision="allowed", reason="t",
                                 standalone_question="How do I search for tickets?"), **kw)


def test_second_turn_scope_prompt_contains_first_turn(catalog, ticket_chunk):
    fake = allowed_fake()
    g = make_graph(catalog, fake, ticket_chunk)
    send(g, "how do I search for tickets?")
    send(g, "and how do I edit it?")
    second_prompt = fake.calls[1][1][1]
    assert "Conversation so far:" in second_prompt
    assert "how do I search for tickets?" in second_prompt
    assert "FAKE STEPS" in second_prompt  # the previous answer is there too


def test_sessions_are_isolated(catalog, ticket_chunk):
    fake = allowed_fake()
    g = make_graph(catalog, fake, ticket_chunk)
    send(g, "how do I search for tickets?", session="alice")
    send(g, "hello again", session="bob")
    bob_prompt = fake.calls[1][1][1]
    assert "Conversation so far:" not in bob_prompt  # bob never saw alice's history


def test_retrieval_uses_the_standalone_rewrite(catalog, ticket_chunk):
    fake = FakeLLM(ScopeDecision(decision="allowed", reason="t",
                                 standalone_question="How do I edit a ticket?"))
    index = FakeIndex(hits=[(ticket_chunk, 0.9)])
    g = build_graph(catalog, llm=fake, index=index, checkpointer=InMemorySaver())
    send(g, "and how do I edit it?")
    assert index.searches[0][0] == "How do I edit a ticket?"


def test_refused_turns_are_not_recorded(catalog, ticket_chunk):
    fake = FakeLLM(ScopeDecision(decision="not_allowed", reason="t"))
    g = make_graph(catalog, fake, ticket_chunk)
    send(g, "how do I void an invoice?")
    fake.result = ScopeDecision(decision="allowed", reason="t", standalone_question="q2")
    send(g, "how do I search for tickets?")
    assert "Conversation so far:" not in fake.calls[1][1][1]  # refusal left no trace


def test_transients_do_not_leak_between_turns(catalog, ticket_chunk):
    fake = allowed_fake()
    g = make_graph(catalog, fake, ticket_chunk)
    bad = dict(MENU, is_maintenance=True)
    req = ChatRequest(user_id="u1", session_id="s1", message="hi", ui_lang="en", menu=bad)
    out1 = g.invoke(initial_state(req), config={"configurable": {"thread_id": "s1"}})
    assert out1["error"]
    out2 = send(g, "how do I search for tickets?")
    assert out2["error"] is None
    assert out2["answer"] == "FAKE STEPS"  # turn 1's error did not poison turn 2


def test_record_turn_only_records_answered():
    state = {"answered": False, "message": "m", "answer": "x", "history": []}
    assert record_turn(state) == {}
    state["answered"] = True
    assert record_turn(state) == {"history": [{"user": "m", "assistant": "x"}]}


def test_compaction_folds_old_turns_into_summary(catalog, ticket_chunk):
    fake = allowed_fake(answer="SUMMARY OF OLD TURNS")
    settings = get_settings()
    node = make_compact_history(lambda: fake, settings)
    history = [{"user": f"q{i}", "assistant": f"a{i}"} for i in range(10)]
    out = node({"history": history, "summary": ""})
    assert out["summary"] == "SUMMARY OF OLD TURNS"
    assert out["history"] == history[-settings.history_keep_turns:]
    prompt = fake.answer_calls[0][0][1]
    assert "q0" in prompt and "q3" in prompt  # the folded-away turns went to the summarizer


def test_compaction_is_skipped_below_threshold():
    node = make_compact_history(lambda: FakeLLM(), get_settings())
    assert node({"history": [{"user": "q", "assistant": "a"}] * 3, "summary": ""}) == {}


def test_compaction_failure_keeps_history(caplog):
    node = make_compact_history(lambda: FakeLLM(answer_exc=TimeoutError("down")), get_settings())
    history = [{"user": f"q{i}", "assistant": f"a{i}"} for i in range(10)]
    assert node({"history": history, "summary": ""}) == {}  # fail OPEN: nothing lost


def test_compaction_triggers_through_the_graph(catalog, ticket_chunk):
    fake = allowed_fake(answer="STEPS")
    g = make_graph(catalog, fake, ticket_chunk)
    settings = get_settings()
    for i in range(settings.compact_after_turns + 1):  # 9 answered turns
        out = send(g, f"question number {i}")
    assert len(out["history"]) == settings.history_keep_turns
    assert out["summary"]  # old turns live in the summary now
