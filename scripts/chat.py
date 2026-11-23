"""Interactive terminal chat with the full pipeline, WITH memory (real Gemini).

    python scripts/chat.py real_menu.json          # English session
    python scripts/chat.py real_menu.json ar       # Arabic session

Commands inside the chat:  /new  start a fresh session (forgets everything)
                           /exit quit
Every exchange is appended to last_run.txt (open it in VSCode to read Arabic).
With DATABASE_URL in .env, memory is in Postgres and every turn is logged to the history
tables (chat_sessions / chat_messages); without it, memory is in RAM and nothing is logged.
"""

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.database import open_pool  # noqa: E402
from app.core.tracing import flush  # noqa: E402
from app.features.agent.schemas import ChatRequest  # noqa: E402
from app.features.agent.services.graph import build_graph  # noqa: E402
from app.features.conversation.repositories.checkpointer import get_checkpointer  # noqa: E402
from app.features.conversation.repositories.history import (  # noqa: E402
    BackgroundHistoryWriter,
    ChatHistoryRepository,
)
from app.features.conversation.services.chat_service import ChatService  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print(__doc__)
        return
    menu = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    ui_lang = sys.argv[2] if len(sys.argv) > 2 else "en"
    settings = get_settings()
    pool = open_pool(settings) if settings.database_url else None
    # Same wiring as the app: history rows are written in the background.
    history = BackgroundHistoryWriter(ChatHistoryRepository(pool, settings.db_schema)) if pool else None
    try:
        graph = build_graph(settings=settings, checkpointer=get_checkpointer(settings, pool))
        chat_loop(ChatService(graph, settings, history), menu, ui_lang)
    finally:  # also when a turn crashes: the waiting turns are written, the pool closes cleanly
        flush()  # push any queued Langfuse events before the process exits
        if history is not None:
            history.close()
        if pool is not None:
            pool.close()


def chat_loop(chat: ChatService, menu: dict, ui_lang: str) -> None:
    session = str(uuid.uuid4())[:8]
    log_path = ROOT / "last_run.txt"
    log_path.write_text("", encoding="utf-8")
    print(f"session {session} started ({ui_lang}). /new = fresh session, /exit = quit.\n")

    while True:
        try:
            message = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message:
            continue
        if message == "/exit":
            break
        if message == "/new":
            session = str(uuid.uuid4())[:8]
            print(f"-- new session {session} (history forgotten)\n")
            continue
        req = ChatRequest(
            user_id="cli", user_name="CLI tester", session_id=session, message=message, ui_lang=ui_lang, menu=menu
        )
        out = chat.run(req)
        line = (
            f"[{out.get('scope') or 'error'}"
            + (f" | q: {out['standalone_question']}" if out.get("standalone_question") else "")
            + f" | history: {len(out.get('history') or [])} turns]"
        )
        print(f"\n{line}\nbot > {out.get('answer') or '(no reply text)'}\n")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"you > {message}\n{line}\nbot > {out.get('answer', '')}\n\n")


if __name__ == "__main__":
    main()
