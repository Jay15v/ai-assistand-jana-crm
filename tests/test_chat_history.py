"""Chat history logging.

Part 1 needs nothing: the service with a fake history repository.
Part 2 needs a throwaway Postgres (never the shared CRM database). It is skipped unless
TEST_DATABASE_URL is set, e.g.
    docker run -d --name crm-test-pg -e POSTGRES_PASSWORD=test -e POSTGRES_DB=crm_test -p 55432:5432 postgres:16-alpine
    $env:TEST_DATABASE_URL = "postgresql://postgres:test@localhost:55432/crm_test"
Each Postgres test drops and recreates the ai_assisstant schema from sql/chat_history.sql.
"""

import json
import os
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import ROOT_DIR, Settings, get_settings
from app.core.database import open_pool, to_libpq_url
from app.features.agent.repositories.manual import load_chunks
from app.features.agent.repositories.tabs import TabCatalog
from app.features.agent.schemas import ChatRequest
from app.features.agent.services.graph import build_graph
from app.features.agent.services.scope import ScopeDecision
from app.features.conversation.repositories.checkpointer import get_checkpointer
from app.features.conversation.repositories.history import (
    BackgroundHistoryWriter,
    ChatHistoryRepository,
    Turn,
)
from app.features.conversation.services.chat_service import ChatService
from app.main import create_app
from tests.conftest import FakeIndex, FakeLLM

FIXTURES = Path(__file__).parent / "fixtures"
MENU = json.loads((FIXTURES / "menu_admin.json").read_text(encoding="utf-8"))
NO_TRACING = Settings(_env_file=None, langfuse_public_key=None, langfuse_secret_key=None)
TEST_DB = os.environ.get("TEST_DATABASE_URL")
SCHEMA = "ai_assisstant"


@pytest.fixture(scope="module")
def catalog():
    return TabCatalog.from_settings(get_settings())


@pytest.fixture(scope="module")
def chunk():
    return next(c for c in load_chunks() if c.question_en == "How do I search for tickets?")


def body(**overrides) -> dict:
    base = {"user_id": "u1", "user_name": "Test User", "session_id": "s1",
            "message": "how do I search for tickets?", "ui_lang": "en", "menu": MENU}
    return {**base, **overrides}


def allowed_llm() -> FakeLLM:
    return FakeLLM(ScopeDecision(decision="allowed", reason="ok", standalone_question="How do I search for tickets?"))


class FakeHistory:
    def __init__(self, fail: bool = False):
        self.turns: list[Turn] = []
        self.fail = fail

    def log_turn(self, turn: Turn) -> int:
        if self.fail:
            raise RuntimeError("database down")
        self.turns.append(turn)
        return len(self.turns)


def client_for(catalog, chunk, llm, history, checkpointer=None) -> TestClient:
    graph = build_graph(catalog, llm=llm, index=FakeIndex(hits=[(chunk, 0.9)]),
                        checkpointer=checkpointer or InMemorySaver())
    return TestClient(create_app(ChatService(graph, NO_TRACING, history)))


# ---------------------------------------------------------------- the CRM-style URL

def test_node_style_url_is_made_acceptable_to_python():
    url = "postgresql://u:p%40ss@host:5432/db?schema=ai_x&sslmode=no-verify"
    assert to_libpq_url(url) == "postgresql://u:p%40ss@host:5432/db?sslmode=require"


def test_other_url_settings_are_left_alone():
    url = "postgresql://u:p@host/db?sslmode=verify-full&connect_timeout=5"
    assert to_libpq_url(url) == url
    assert to_libpq_url("postgresql://u:p@host/db") == "postgresql://u:p@host/db"


# ---------------------------------------------------------------- part 1: the service

def test_answered_turn_is_logged_with_every_field(catalog, chunk):
    history = FakeHistory()
    with client_for(catalog, chunk, allowed_llm(), history) as client:
        client.post("/chat", json=body(ui_lang="ar-EG"))
    (turn,) = history.turns
    assert (turn.user_id, turn.session_id, turn.user_name) == ("u1", "s1", "Test User")
    assert turn.user_message == "how do I search for tickets?"
    assert turn.standalone_question == "How do I search for tickets?"
    assert (turn.answer, turn.scope, turn.scope_reason) == ("FAKE STEPS", "allowed", "ok")
    assert turn.ui_lang == "ar"  # stored normalised
    assert turn.latency_ms >= 0


@pytest.mark.parametrize("llm, scope", [
    (FakeLLM(ScopeDecision(decision="not_allowed", reason="r")), "not_allowed"),
    (FakeLLM(ScopeDecision(decision="off_topic", reason="r")), "off_topic"),
    (FakeLLM(exc=RuntimeError("gemini down")), "error"),
])
def test_refused_off_topic_and_failed_turns_are_logged_too(catalog, chunk, llm, scope):
    history = FakeHistory()
    with client_for(catalog, chunk, llm, history) as client:
        res = client.post("/chat", json=body())
    (turn,) = history.turns
    assert turn.scope == scope
    assert turn.answer == res.json()["answer"]  # exactly what the user saw


def test_database_failure_does_not_break_the_chat(catalog, chunk):
    with client_for(catalog, chunk, allowed_llm(), FakeHistory(fail=True)) as client:
        res = client.post("/chat", json=body())
    assert res.status_code == 200
    assert res.json()["answer"] == "FAKE STEPS"


def test_crashed_turn_is_logged_as_error_then_raised():
    class Boom:
        def stream(self, *a, **k):
            raise RuntimeError("graph crashed")

    history = FakeHistory()
    service = ChatService(Boom(), NO_TRACING, history)

    with pytest.raises(RuntimeError):
        service.send(ChatRequest(**body()))
    (turn,) = history.turns
    assert (turn.scope, turn.user_message, turn.answer) == ("error", "how do I search for tickets?", "")
    assert turn.standalone_question is None


class CrashingIndex(FakeIndex):
    """A manual search that breaks from the Nth search on (an error no graph step handles)."""

    def __init__(self, hits, crash_from: int = 1):
        super().__init__(hits)
        self.crash_from = crash_from

    def search(self, query, allowed_names, top_k=3):
        if len(self.searches) + 1 >= self.crash_from:
            raise RuntimeError("vector store down")
        return super().search(query, allowed_names, top_k)


def test_turn_that_crashes_halfway_keeps_what_the_finished_steps_produced(catalog, chunk):
    """The scope step finished, the search crashed: the row keeps the scope step's output."""
    history = FakeHistory()
    graph = build_graph(catalog, llm=allowed_llm(), index=CrashingIndex([(chunk, 0.9)]),
                        checkpointer=InMemorySaver())
    service = ChatService(graph, NO_TRACING, history)

    with pytest.raises(RuntimeError, match="vector store down"):
        service.send(ChatRequest(**body()))
    (turn,) = history.turns
    assert turn.user_message == "how do I search for tickets?"
    assert turn.standalone_question == "How do I search for tickets?"
    assert turn.scope_reason == "ok"
    assert (turn.scope, turn.answer) == ("error", "")  # marked crashed; no answer was written
    assert turn.latency_ms >= 0


def test_crashed_turn_carries_nothing_over_from_the_turn_before(catalog, chunk):
    """Same chat, turn 1 answered, turn 2 crashes: row 2 holds turn 2's own data only."""
    history = FakeHistory()
    llm = allowed_llm()
    graph = build_graph(catalog, llm=llm, index=CrashingIndex([(chunk, 0.9)], crash_from=2),
                        checkpointer=InMemorySaver())
    service = ChatService(graph, NO_TRACING, history)

    service.send(ChatRequest(**body()))
    llm.result = ScopeDecision(decision="allowed", reason="second", standalone_question="How do I print a ticket?")
    with pytest.raises(RuntimeError):
        service.send(ChatRequest(**body(message="and how do I print one?")))

    first, second = history.turns
    assert (first.scope, first.answer) == ("allowed", "FAKE STEPS")
    assert second.user_message == "and how do I print one?"
    assert second.standalone_question == "How do I print a ticket?"
    assert (second.scope, second.scope_reason, second.answer) == ("error", "second", "")


def test_invalid_request_is_not_logged(catalog, chunk):
    history = FakeHistory()
    with client_for(catalog, chunk, allowed_llm(), history) as client:
        client.post("/chat", json=body(message=""))
    assert history.turns == []


def test_chat_memory_survives_a_crashed_turn(catalog, chunk):
    """Memory is saved once per turn. A turn that crashes must neither lose the chat so far
    nor get into it: the next turn still remembers turn 1, and only turn 1."""
    index = CrashingIndex([(chunk, 0.9)], crash_from=2)
    graph = build_graph(catalog, llm=allowed_llm(), index=index, checkpointer=InMemorySaver())
    service = ChatService(graph, NO_TRACING, FakeHistory())

    service.run(ChatRequest(**body()))
    with pytest.raises(RuntimeError):
        service.run(ChatRequest(**body(message="this one crashes")))
    index.crash_from = 99  # the search works again
    out = service.run(ChatRequest(**body(message="and how do I print one?")))

    assert [t["user"] for t in out["history"]] == ["how do I search for tickets?", "and how do I print one?"]


# ---------------------------------------------------------------- the background writer

class GatedHistory(FakeHistory):
    """A slow database: every write waits until the test opens the gate."""

    def __init__(self):
        super().__init__()
        self.gate = threading.Event()

    def log_turn(self, turn: Turn) -> int:
        assert self.gate.wait(5)
        return super().log_turn(turn)


def test_background_writer_writes_every_turn_in_order_by_the_time_it_closes():
    repo = FakeHistory()
    writer = BackgroundHistoryWriter(repo)
    for i in range(20):
        writer.log_turn(turn(user_message=f"m{i}"))
    writer.close()
    assert [t.user_message for t in repo.turns] == [f"m{i}" for i in range(20)]


def test_background_writer_does_not_wait_for_the_database():
    repo = GatedHistory()
    writer = BackgroundHistoryWriter(repo)
    writer.log_turn(turn())  # returns although the write itself is still blocked
    assert repo.turns == []
    repo.gate.set()
    writer.close()
    assert len(repo.turns) == 1


def test_background_writer_carries_on_after_a_failed_write(caplog):
    class FailsOnBad(FakeHistory):
        def log_turn(self, turn: Turn) -> int:
            if turn.user_message == "bad":
                raise RuntimeError("database down")
            return super().log_turn(turn)

    repo = FailsOnBad()
    writer = BackgroundHistoryWriter(repo)
    writer.log_turn(turn(user_message="bad"))
    writer.log_turn(turn(user_message="good"))
    writer.close()
    assert [t.user_message for t in repo.turns] == ["good"]
    assert "chat history write failed" in caplog.text


def test_background_writer_drops_new_turns_when_too_many_are_waiting(caplog):
    repo = GatedHistory()
    writer = BackgroundHistoryWriter(repo, max_pending=2)
    for i in range(5):
        writer.log_turn(turn(user_message=f"m{i}"))  # never blocks, never raises
    repo.gate.set()
    writer.close()
    assert [t.user_message for t in repo.turns] == ["m0", "m1"]
    assert caplog.text.count("backlog is full") == 3


def test_background_writer_close_does_not_hang_on_a_stuck_database(caplog):
    repo = GatedHistory()
    writer = BackgroundHistoryWriter(repo)
    writer.log_turn(turn())
    writer.log_turn(turn())
    started = time.perf_counter()
    writer.close(timeout=0.2)
    assert time.perf_counter() - started < 2
    assert "2 turn(s) not written" in caplog.text
    repo.gate.set()  # let the worker thread go
    writer.log_turn(turn())  # after close: dropped with a log line, never an exception
    assert "writer is closed" in caplog.text


def test_chat_through_the_background_writer_logs_the_turn(catalog, chunk):
    repo = FakeHistory()
    writer = BackgroundHistoryWriter(repo)
    with client_for(catalog, chunk, allowed_llm(), writer) as client:
        res = client.post("/chat", json=body())
    writer.close()
    assert res.json()["answer"] == "FAKE STEPS"
    assert [(t.scope, t.answer) for t in repo.turns] == [("allowed", "FAKE STEPS")]


# ---------------------------------------------------------------- part 2: real Postgres

needs_db = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set (throwaway Postgres only)")


@pytest.fixture
def pool():
    import psycopg

    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.execute(f"CREATE SCHEMA {SCHEMA}")
        conn.execute((ROOT_DIR / "sql" / "chat_history.sql").read_text(encoding="utf-8"))
    # Node/Prisma-style extras on purpose: open_pool must cope with them.
    settings = Settings(_env_file=None, DATABASE_URL=TEST_DB + "?schema=whatever")
    p = open_pool(settings)
    yield p
    p.close()


def rows(pool, query, *args):
    with pool.connection() as conn:
        return conn.execute(query, args).fetchall()


def turn(user="u1", session="s1", **kw) -> Turn:
    base = dict(user_id=user, session_id=session, user_name="Test User", user_message="hi",
                standalone_question=None, answer="a", scope="allowed", scope_reason=None,
                ui_lang="en", latency_ms=5)
    return Turn(**{**base, **kw})


@needs_db
def test_turns_are_numbered_and_the_session_counts_them(pool):
    repo = ChatHistoryRepository(pool, SCHEMA)
    assert [repo.log_turn(turn()), repo.log_turn(turn())] == [1, 2]
    (s,) = rows(pool, "SELECT * FROM ai_assisstant.chat_sessions")
    assert (s["user_id"], s["session_id"], s["turn_count"]) == ("u1", "s1", 2)
    assert s["last_message_at"] >= s["started_at"]
    assert [r["turn_no"] for r in rows(pool, "SELECT turn_no FROM ai_assisstant.chat_messages ORDER BY id")] == [1, 2]


@needs_db
def test_same_session_id_for_two_users_is_two_chats(pool):
    repo = ChatHistoryRepository(pool, SCHEMA)
    repo.log_turn(turn(user="alice"))
    repo.log_turn(turn(user="bob"))
    sessions = rows(pool, "SELECT user_id, turn_count FROM ai_assisstant.chat_sessions ORDER BY user_id")
    assert [(s["user_id"], s["turn_count"]) for s in sessions] == [("alice", 1), ("bob", 1)]


@needs_db
def test_arabic_text_is_stored_exactly(pool):
    text = "ازاي اضيف شكوى جديدة؟"
    ChatHistoryRepository(pool, SCHEMA).log_turn(turn(user_message=text, answer=text, ui_lang="ar"))
    (m,) = rows(pool, "SELECT user_message, answer, ui_lang FROM ai_assisstant.chat_messages")
    assert (m["user_message"], m["answer"], m["ui_lang"]) == (text, text, "ar")


@needs_db
def test_messages_sent_at_the_same_moment_get_different_numbers(pool):
    repo = ChatHistoryRepository(pool, SCHEMA)
    threads = [threading.Thread(target=repo.log_turn, args=(turn(),)) for _ in range(15)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    numbers = sorted(r["turn_no"] for r in rows(pool, "SELECT turn_no FROM ai_assisstant.chat_messages"))
    assert numbers == list(range(1, 16))
    assert rows(pool, "SELECT turn_count FROM ai_assisstant.chat_sessions")[0]["turn_count"] == 15


@needs_db
def test_background_writer_writes_real_rows_in_order(pool):
    writer = BackgroundHistoryWriter(ChatHistoryRepository(pool, SCHEMA))
    for i in range(1, 6):
        writer.log_turn(turn(user_message=f"m{i}"))
    writer.close()
    msgs = rows(pool, "SELECT turn_no, user_message FROM ai_assisstant.chat_messages ORDER BY id")
    assert [(m["turn_no"], m["user_message"]) for m in msgs] == [(i, f"m{i}") for i in range(1, 6)]
    assert rows(pool, "SELECT turn_count FROM ai_assisstant.chat_sessions")[0]["turn_count"] == 5


@needs_db
def test_a_rejected_row_leaves_nothing_half_written(pool):
    repo = ChatHistoryRepository(pool, SCHEMA)
    repo.log_turn(turn())
    with pytest.raises(Exception):
        repo.log_turn(turn(scope="banana"))  # blocked by the CHECK rule
    assert rows(pool, "SELECT turn_count FROM ai_assisstant.chat_sessions")[0]["turn_count"] == 1
    assert len(rows(pool, "SELECT id FROM ai_assisstant.chat_messages")) == 1


@needs_db
def test_memory_tables_go_into_the_bot_schema_not_public(pool):
    get_checkpointer(NO_TRACING, pool)
    found = rows(pool, "SELECT table_schema, table_name FROM information_schema.tables "
                       "WHERE table_name LIKE 'checkpoint%%' ORDER BY table_name")
    assert {r["table_schema"] for r in found} == {SCHEMA}
    assert {r["table_name"] for r in found} >= {"checkpoints", "checkpoint_blobs", "checkpoint_writes"}


@needs_db
def test_chat_memory_is_saved_once_per_turn(pool, catalog, chunk):
    """One checkpoint row per turn (it was one per graph step), and the memory still works."""
    llm = allowed_llm()
    with client_for(catalog, chunk, llm, None, get_checkpointer(NO_TRACING, pool)) as client:
        client.post("/chat", json=body())
        assert rows(pool, "SELECT count(*) AS n FROM ai_assisstant.checkpoints")[0]["n"] == 1
        client.post("/chat", json=body(message="and how do I print one?"))
        assert rows(pool, "SELECT count(*) AS n FROM ai_assisstant.checkpoints")[0]["n"] == 2
    assert "FAKE STEPS" in str(llm.calls[1])  # turn 2's prompt carried turn 1's answer


@needs_db
def test_full_chat_logs_rows_and_memory_survives_a_restart(pool, catalog, chunk):
    """Two turns, then a new app with a new pool (a restart), then a follow-up in the same chat."""
    llm = allowed_llm()
    repo = ChatHistoryRepository(pool, SCHEMA)
    with client_for(catalog, chunk, llm, repo, get_checkpointer(NO_TRACING, pool)) as client:
        client.post("/chat", json=body())
        client.post("/chat", json=body(message="hello!"))

    settings = Settings(_env_file=None, DATABASE_URL=TEST_DB)
    pool2 = open_pool(settings)
    try:
        repo2 = ChatHistoryRepository(pool2, SCHEMA)
        with client_for(catalog, chunk, llm, repo2, get_checkpointer(NO_TRACING, pool2)) as client:
            client.post("/chat", json=body(message="and how do I print one?"))
    finally:
        pool2.close()

    assert "FAKE STEPS" in str(llm.calls[2])  # the restarted app still remembered the chat
    msgs = rows(pool, "SELECT turn_no, user_message, scope FROM ai_assisstant.chat_messages ORDER BY id")
    assert [(m["turn_no"], m["user_message"]) for m in msgs] == [
        (1, "how do I search for tickets?"), (2, "hello!"), (3, "and how do I print one?")]
