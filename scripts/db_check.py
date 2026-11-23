"""Read-only check of the database the chat writes to (the same DATABASE_URL the app uses).

    python scripts/db_check.py

Prints where it connected and what is in the bot's schema. Writes nothing. Never prints the URL.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import to_libpq_url  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    s = get_settings()
    if not s.database_url:
        print("DATABASE_URL is not set: the chat keeps memory in RAM and logs nothing.")
        return
    with psycopg.connect(to_libpq_url(s.database_url), connect_timeout=15) as conn:
        db, user, addr = conn.execute("SELECT current_database(), current_user, inet_server_addr()").fetchone()
        print(f"database: {db} | user: {user} | server address: {addr}")
        print(f"schema the bot uses: {s.db_schema}")

        print("\nwhere the bot's tables are (any schema):")
        for schema, table in conn.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_name IN ('chat_sessions', 'chat_messages') OR table_name LIKE 'checkpoint%%' "
            "ORDER BY 1, 2"
        ):
            print(f"  {schema}.{table}")

        try:
            sessions = conn.execute(
                f"SELECT user_id, session_id, turn_count, last_message_at FROM {s.db_schema}.chat_sessions "
                "ORDER BY last_message_at DESC LIMIT 5"
            ).fetchall()
            count = conn.execute(f"SELECT count(*) FROM {s.db_schema}.chat_messages").fetchone()[0]
        except psycopg.Error as exc:
            print(f"\ncannot read {s.db_schema}.chat_sessions: {exc}")
            return
        print(f"\n{s.db_schema}.chat_messages: {count} rows")
        print(f"{s.db_schema}.chat_sessions, latest 5:")
        for row in sessions:
            print("  ", *row)


if __name__ == "__main__":
    main()
