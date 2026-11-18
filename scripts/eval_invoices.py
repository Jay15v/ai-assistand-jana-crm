"""Invoice-domain evaluation with REAL Gemini: every invoice possibility, end to end.

    python scripts/eval_invoices.py

Covers every manual-documented invoice flow (create, search, details, collect, void x2,
refund x2, review refunds, EOD, Full EOD, export), permissions from other roles, partial
splits, Arabic / mixed wording, and a multi-turn money conversation.

Full answers are appended to invoices_run.txt (open in VSCode to read Arabic).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.graph.build import build_graph, get_checkpointer  # noqa: E402
from app.graph.state import initial_state  # noqa: E402
from app.models.chat import ChatRequest  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


def load_menu(name: str) -> dict:
    return json.loads((FIXTURES / f"menu_{name}.json").read_text(encoding="utf-8"))


# (title, menu, [turns]); turn = (message, ui_lang, acceptable scopes); () = just observe.
CASES = [
    # --- every documented flow, invoices_only role ---------------------------
    ("create a manual invoice", "invoices_only", [
        ("how do I create a new invoice?", "en", {"allowed"}),
    ]),
    ("search invoices", "invoices_only", [
        ("how do I find an old invoice?", "en", {"allowed"}),
    ]),
    ("invoice details page", "invoices_only", [
        ("what can I see on the invoice page?", "en", {"allowed"}),
    ]),
    ("collect payment", "invoices_only", [
        ("how do I collect the money for a pending invoice?", "en", {"allowed"}),
    ]),
    ("void request", "invoices_only", [
        ("how do I ask to cancel an invoice?", "en", {"allowed"}),
    ]),
    ("void directly", "invoices_only", [
        ("how do I void an invoice immediately without a request?", "en", {"allowed"}),
    ]),
    ("refund request", "invoices_only", [
        ("how do I submit a refund request?", "en", {"allowed"}),
    ]),
    ("refund directly", "invoices_only", [
        ("how do I refund an invoice right away?", "en", {"allowed"}),
    ]),
    ("review refund requests (AR)", "invoices_only", [
        ("ازاي اراجع طلبات الاسترداد واوافق عليها؟", "ar", {"allowed"}),
    ]),
    ("end of day", "invoices_only", [
        ("how do I settle my end of day?", "en", {"allowed"}),
    ]),
    ("full end of day", "invoices_only", [
        ("how do I see the end of day for all employees?", "en", {"allowed"}),
    ]),
    ("export invoices to excel", "invoices_only", [
        ("how do I download the invoice search results as excel?", "en", {"allowed"}),
    ]),
    # --- permissions edges ----------------------------------------------------
    ("reports tab not in this menu", "invoices_only", [
        ("how do I run the daily invoices report?", "en", {"not_allowed"}),
    ]),
    ("invoices for a readonly user", "readonly_role", [
        ("how do I create an invoice?", "en", {"not_allowed"}),
    ]),
    ("partial: refund + ticket", "invoices_only", [
        ("how do I refund an invoice and also create a new ticket?", "en", {"partial"}),
    ]),
    # --- tricky wording -------------------------------------------------------
    ("AR: customer wants money back", "invoices_only", [
        ("ازاي ارجع فلوس فاتورة للعميل؟", "ar", {"allowed"}),
    ]),
    ("AR: collected by mistake", "invoices_only", [
        ("عايز الغي فاتورة اتحصلت بالغلط", "ar", {"allowed"}),
    ]),
    ("mixed: refund vs void choice", "invoices_only", [
        ("what is the difference between refund and void?", "en", ()),
    ]),
    ("invoice statuses (intro text, not a section)", "invoices_only", [
        ("what are the possible invoice statuses?", "en", ()),
    ]),
    # --- a full money conversation (memory) -----------------------------------
    ("multi-turn: create -> collect -> money back", "invoices_only", [
        ("how do I create a manual invoice?", "en", {"allowed"}),
        ("and how do I collect it?", "en", {"allowed"}),
        ("and if the customer wants their money back later?", "en", {"allowed"}),
    ]),
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    graph = build_graph(checkpointer=get_checkpointer())
    menus = {name: load_menu(name) for name in {m for _, m, _ in CASES}}
    log_path = ROOT / "invoices_run.txt"
    log_path.write_text("", encoding="utf-8")
    passed = 0

    for c, (title, menu_name, turns) in enumerate(CASES):
        session = f"inv-{c}"
        problems: list[str] = []
        report: list[str] = [f"=== case {c + 1}: {title}  [menu: {menu_name}] ==="]
        for message, lang, want in turns:
            req = ChatRequest(user_id="e", session_id=session, message=message,
                              ui_lang=lang, menu=menus[menu_name])
            out = graph.invoke(initial_state(req), config={"configurable": {"thread_id": session}})
            scope = out.get("scope")
            section = out["sections"][0].question_en if out.get("sections") else None
            report.append(f"you > {message}")
            report.append(f"[{scope or 'error'}"
                          + (f" | q: {out['standalone_question']}" if out.get("standalone_question") else "")
                          + (f" | section: {section}" if section else "")
                          + "]")
            report.append(f"bot > {out.get('answer') or '(no reply text)'}\n")
            if want and scope not in want:
                problems.append(f"{message!r}: scope={scope} (wanted one of {sorted(want)})")
        ok = not problems
        passed += ok
        verdict = "PASS" if ok else ("INFO" if not any(w for *_, w in turns) else "FAIL")
        print(f"[{verdict}] {c + 1:2d}. {title}  -> " + ", ".join(
            line.split(" | ")[0].strip("[]") for line in report if line.startswith("[")))
        for p in problems:
            print(f"        {p}")
        with log_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(report) + "\n")

    print(f"\npassed: {passed}/{len(CASES)}  (full answers in invoices_run.txt)")


if __name__ == "__main__":
    main()
