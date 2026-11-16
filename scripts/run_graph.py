"""Hand-test the chatbot graph with a menu JSON and a question.

    python scripts/run_graph.py real_menu.json "how do I add a ticket?"
    python scripts/run_graph.py real_menu.json "ازاي اضيف تذكرة" ar
    python scripts/run_graph.py real_menu.json "how do I add a ticket?" ar-EG

The 3rd argument is the CRM language switch (ui_lang, default "en"). It goes through the same
ChatRequest validation as the real API: "ar-EG" -> "ar", unknown values such as "fr" are rejected.
"""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.graph.build import build_graph  # noqa: E402
from app.graph.state import initial_state  # noqa: E402
from app.models.chat import ChatRequest  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3:
        print(__doc__)
        return
    menu_path, message = Path(sys.argv[1]), sys.argv[2]
    ui_lang = sys.argv[3] if len(sys.argv) > 3 else "en"
    try:
        request = ChatRequest(
            user_id="cli",
            session_id="cli",
            message=message,
            ui_lang=ui_lang,
            menu=json.loads(menu_path.read_text(encoding="utf-8")),
        )
    except ValidationError as exc:
        print(f"REQUEST REJECTED (the real API would answer HTTP 422):\n{exc}")
        return

    graph = build_graph()
    path: list[str] = []
    final: dict = {}
    for update in graph.stream(initial_state(request), stream_mode="updates"):
        for node, values in update.items():
            path.append(node)
            final.update(values or {})

    print(f"question : {message}  (ui_lang {ui_lang!r} -> {request.ui_lang})")
    print(f"path     : START -> {' -> '.join(path)} -> END")
    if final.get("error"):
        print(f"error    : {final['error']}")
    else:
        print(f"allowed  : {len(final['allowed_tabs'])}  ->  " + ", ".join(t.name_en for t in final["allowed_tabs"]))
        print(f"not allowed: {len(final['not_allowed_tabs'])}")
        if final.get("unknown_tabs"):
            print(f"unknown  : {final['unknown_tabs']}")
    if final.get("scope"):
        print(f"decision : {final['scope']}   ({final.get('scope_reason', '')})")
        if final["scope"] == "partial":
            print(f"  answerable part : {final.get('allowed_question')}")
            print(f"  blocked part    : {final.get('not_allowed_question')}")
    if final.get("answer"):
        print(f"answer   : {final['answer']}")


if __name__ == "__main__":
    main()
