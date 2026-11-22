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

from app.features.agent.schemas import ChatRequest  # noqa: E402
from app.features.agent.services.graph import build_graph  # noqa: E402
from app.features.agent.services.state import initial_state  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    out_lines: list[str] = []

    def emit(text: str = "") -> None:
        print(text)
        out_lines.append(text)

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

    emit(f"question : {message}  (ui_lang {ui_lang!r} -> {request.ui_lang})")
    emit(f"path     : START -> {' -> '.join(path)} -> END")
    if final.get("error"):
        emit(f"error    : {final['error']}")
    else:
        emit(f"allowed  : {len(final['allowed_tabs'])}  ->  " + ", ".join(t.name_en for t in final["allowed_tabs"]))
        emit(f"not allowed: {len(final['not_allowed_tabs'])}")
        if final.get("unknown_tabs"):
            emit(f"unknown  : {final['unknown_tabs']}")
    if final.get("scope"):
        emit(f"decision : {final['scope']}   ({final.get('scope_reason', '')})")
        if final["scope"] == "partial":
            emit(f"  answerable part : {final.get('allowed_question')}")
            emit(f"  blocked part    : {final.get('not_allowed_question')}")
    if final.get("sections") is not None:
        emit("sections : " + (", ".join(c.question_en for c in final["sections"]) or "(none)"))
    if final.get("answer"):
        emit(f"\nANSWER:\n{final['answer']}")

    # Arabic does not render in Windows terminals (no RTL shaping) - read it from this file instead.
    out = Path(__file__).resolve().parent.parent / "last_run.txt"
    out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"\n(saved to {out.name} - open it in VSCode to read Arabic properly)")


if __name__ == "__main__":
    main()
