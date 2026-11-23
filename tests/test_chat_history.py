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
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import ROOT_DIR, Settings, get_settings
from app.core.database import open_pool, to_libpq_url
from app.features.agent.repositories.manual import load_chunks
from app.features.agent.repositories.tabs import TabCatalog
from app.features.agent.services.graph import build_graph
from app.features.agent.services.scope import ScopeDecision
from app.features.conversation.repositories.checkpointer import get_checkpointer
from app.features.conversation.repositories.history import ChatHistoryRepository, Turn
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
        def invoke(self, *a, **k):
            raise RuntimeError("graph crashed")

    history = FakeHistory()
    service = ChatService(Boom(), NO_TRACING, history)
    from app.features.agent.schemas import ChatRequest

    with pytest.raises(RuntimeError):
        service.send(ChatRequest(**body()))
    assert [t.scope for t in history.turns] == ["error"]


def test_invalid_request_is_not_logged(catalog, chunk):
    history = FakeHistory()
    with client_for(catalog, chunk, allowed_llm(), history) as client:
        client.post("/chat", json=body(message=""))
    assert history.turns == []


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
