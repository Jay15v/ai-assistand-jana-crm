"""Multi-turn evaluation of chat memory with REAL Gemini: follow-ups must resolve from history.

    python scripts/eval_followups.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.features.agent.schemas import ChatRequest  # noqa: E402
from app.features.agent.services.graph import build_graph  # noqa: E402
from app.features.agent.services.state import initial_state  # noqa: E402
from app.features.conversation.repositories.checkpointer import get_checkpointer  # noqa: E402

MENU = json.loads((ROOT / "tests" / "fixtures" / "menu_readonly_role.json").read_text(encoding="utf-8"))

# Each dialogue: list of turns; the LAST turn carries the checks.
# (message, ui_lang, expected scope, expected first retrieved section, words in answer)
DIALOGUES = [
    [
        ("how do I search for tickets?", "en", "allowed", "How do I search for tickets?", []),
        ("and how do I edit it?", "en", "allowed", "How do I edit a ticket?", ["pencil"]),
    ],
    [
        ("ازاي ادور على شكوى؟", "ar", "allowed", "How do I search for a complaint?", []),
        ("وازاي اضيف رد عليها؟", "ar", "allowed", "How do I add a response to a complaint?", []),
    ],
    [
        ("how do I search for tickets?", "en", "allowed", "How do I search for tickets?", []),
        ("how do I print one of them?", "en", "allowed", "How do I print a ticket?", ["print"]),
    ],
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    graph = build_graph(checkpointer=get_checkpointer())
    passed = 0
    for d, dialogue in enumerate(DIALOGUES):
        session = f"eval-{d}"
        problems: list[str] = []
        for message, lang, want_scope, want_section, want_words in dialogue:
            req = ChatRequest(user_id="e", session_id=session, message=message, ui_lang=lang, menu=MENU)
            out = graph.invoke(initial_state(req), config={"configurable": {"thread_id": session}})
            got_section = out["sections"][0].question_en if out.get("sections") else None
            if out.get("scope") != want_scope:
                problems.append(f"{message!r}: scope={out.get('scope')} (want {want_scope})")
            if want_section and got_section != want_section:
                problems.append(f"{message!r}: section={got_section!r} (want {want_section!r})")
            for w in want_words:
                if w.lower() not in (out.get("answer") or "").lower():
                    problems.append(f"{message!r}: answer missing {w!r}")
        ok = not problems
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] dialogue {d + 1}: " + " -> ".join(m for m, *_ in dialogue))
        if out.get("standalone_question"):
            print(f"        last rewrite: {out['standalone_question']}")
        for p in problems:
            print(f"        {p}")
    print(f"\npassed: {passed}/{len(DIALOGUES)}")


if __name__ == "__main__":
    main()
