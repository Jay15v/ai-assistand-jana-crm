"""Interactive terminal chat with the full pipeline, WITH memory (real Gemini).

    python scripts/chat.py real_menu.json          # English session
    python scripts/chat.py real_menu.json ar       # Arabic session

Commands inside the chat:  /new  start a fresh session (forgets everything)
                           /exit quit
Every exchange is appended to last_run.txt (open it in VSCode to read Arabic).
History is in memory for this run (production uses Postgres via DATABASE_URL).
"""

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.graph.build import build_graph, get_checkpointer  # noqa: E402
from app.graph.state import initial_state  # noqa: E402
from app.models.chat import ChatRequest  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print(__doc__)
        return
    menu = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    ui_lang = sys.argv[2] if len(sys.argv) > 2 else "en"
    graph = build_graph(checkpointer=get_checkpointer())
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
        req = ChatRequest(user_id="cli", session_id=session, message=message, ui_lang=ui_lang, menu=menu)
        out = graph.invoke(initial_state(req), config={"configurable": {"thread_id": session}})
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
