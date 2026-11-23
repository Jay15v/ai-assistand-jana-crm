"""The Postgres connection pool, shared by the chat memory (LangGraph checkpointer) and the chat
history log tables. Only used when DATABASE_URL is set."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import Settings


def to_libpq_url(url: str) -> str:
    """Accept the Node/Prisma style URL the CRM backend uses. Python's driver (libpq) rejects
    two of its settings, so: `schema=` is dropped (the schema comes from settings.db_schema),
    and `sslmode=no-verify` becomes `require` (encrypted, server certificate not checked,
    which is what no-verify means in Node). Everything else is passed through unchanged."""
    parts = urlsplit(url)
    params = [
        (key, "require" if key == "sslmode" and value == "no-verify" else value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "schema"
    ]
    return urlunsplit(parts._replace(query=urlencode(params)))


def open_pool(settings: Settings) -> ConnectionPool:
    """Open the pool. Every connection works inside settings.db_schema (search_path), so
    LangGraph's own tables are created there too, not in `public` next to the CRM's tables.

    autocommit / prepare_threshold=0 / dict_row are what LangGraph's PostgresSaver requires.
    A pool (instead of one connection) also replaces a connection the server dropped, so an
    idle timeout on the database does not break the bot until it is restarted."""
    pool = ConnectionPool(
        to_libpq_url(settings.database_url),
        min_size=1,
        max_size=settings.db_pool_max_size,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
            "options": f"-c search_path={settings.db_schema}",
        },
        check=ConnectionPool.check_connection,
        open=False,
    )
    pool.open(wait=True, timeout=30)
    return pool
