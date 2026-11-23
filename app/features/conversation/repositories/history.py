"""The chat history log: chat_sessions (one row per chat) and chat_messages (one row per turn).

Write-only: the bot never reads these tables back (its memory is the checkpointer). The tables
are created by hand from sql/chat_history.sql; this code never creates or alters them."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from psycopg import sql
from psycopg_pool import ConnectionPool

log = logging.getLogger("crm_ai.chat")


@dataclass(frozen=True)
class Turn:
    """One question and its answer, as written to chat_messages."""

    user_id: str
    session_id: str
    user_name: str | None
    user_message: str
    standalone_question: str | None
    answer: str
    scope: str  # allowed | partial | not_allowed | off_topic | error
    scope_reason: str | None
    ui_lang: str  # en | ar
    latency_ms: int


class ChatHistoryRepository:
    def __init__(self, pool: ConnectionPool, schema: str):
        self.pool = pool
        schema_id = sql.Identifier(schema)
        # Start the session or add 1 to it, in one statement, and get the new turn number back.
        # One statement means two messages arriving at once can never get the same number.
        self._upsert_session = sql.SQL(
            """INSERT INTO {schema}.chat_sessions (user_id, session_id, user_name, turn_count)
               VALUES (%s, %s, %s, 1)
               ON CONFLICT (user_id, session_id) DO UPDATE
               SET turn_count = chat_sessions.turn_count + 1, last_message_at = now()
               RETURNING turn_count"""
        ).format(schema=schema_id)
        self._insert_message = sql.SQL(
            """INSERT INTO {schema}.chat_messages
               (user_id, session_id, turn_no, user_message, standalone_question, answer,
                scope, scope_reason, ui_lang, latency_ms)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        ).format(schema=schema_id)

    def log_turn(self, turn: Turn) -> int:
        """Write one turn. Both rows are saved together or not at all. Returns the turn number."""
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(self._upsert_session, (turn.user_id, turn.session_id, turn.user_name)).fetchone()
            turn_no = row["turn_count"] if isinstance(row, dict) else row[0]
            conn.execute(self._insert_message, (
                turn.user_id, turn.session_id, turn_no, turn.user_message, turn.standalone_question,
                turn.answer, turn.scope, turn.scope_reason, turn.ui_lang, turn.latency_ms,
            ))
        return turn_no


class BackgroundHistoryWriter:
    """Writes turns to the history tables in the background, so a reply never waits for the
    database. Same log_turn() as the repository it wraps, so the chat service can use either.

    One worker thread writes the turns one after another: the history log holds at most one
    pool connection however many chats run at once. Three rules keep it safe:
    * a failed write is logged and the worker moves on to the next turn (fail open);
    * at most `max_pending` turns wait in memory - beyond that (the database is down or very
      slow) new turns are dropped with an error log instead of using more and more memory;
    * close() waits a limited time for the waiting turns, so shutdown can never hang.
    A turn still waiting when the process is killed is lost; a normal shutdown writes them all."""

    def __init__(self, repository, max_pending: int = 1000):
        self._repository = repository
        self._max_pending = max_pending
        self._pending = 0  # turns handed over and not yet written
        self._closed = False
        self._state = threading.Condition()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chat-history")

    def log_turn(self, turn: Turn) -> None:
        """Hand the turn over and return at once."""
        with self._state:
            if self._closed:
                log.error("chat history writer is closed: turn not logged (session %s)", turn.session_id)
                return
            if self._pending >= self._max_pending:
                log.error("chat history backlog is full (%d turns): turn not logged (session %s)",
                          self._pending, turn.session_id)
                return
            self._pending += 1
            self._executor.submit(self._write, turn)

    def _write(self, turn: Turn) -> None:
        try:
            self._repository.log_turn(turn)
        except Exception:  # noqa: BLE001 - fail OPEN: the worker must survive any failed write
            log.exception("chat history write failed (session %s)", turn.session_id)
        finally:
            with self._state:
                self._pending -= 1
                self._state.notify_all()

    def close(self, timeout: float = 10.0) -> None:
        """Stop taking turns, give the waiting ones up to `timeout` seconds, then stop."""
        with self._state:
            self._closed = True
            self._state.wait_for(lambda: self._pending == 0, timeout)
            lost = self._pending
        self._executor.shutdown(wait=False, cancel_futures=True)
        if lost:
            log.error("chat history writer stopped with %d turn(s) not written", lost)
