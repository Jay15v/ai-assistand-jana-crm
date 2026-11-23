"""The chat history log: chat_sessions (one row per chat) and chat_messages (one row per turn).

Write-only: the bot never reads these tables back (its memory is the checkpointer). The tables
are created by hand from sql/chat_history.sql; this code never creates or alters them."""

from dataclasses import dataclass

from psycopg import sql
from psycopg_pool import ConnectionPool


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
