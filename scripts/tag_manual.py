"""Tag every ### question of the English manual with the CRM tab(s) it belongs to.

    python scripts/tag_manual.py          # writes app/data/manual/section_tabs.json + prints the table

The proposal rules + the hand review are encoded in SECTION_DEFAULTS / QUESTION_TABS below, so the
tagging is repeatable: rerun after editing the manual and the script fails loudly on any new,
untagged question instead of guessing silently.

Tags use the vector DB's English tab names (the same 54 names step 1 matches against).
A question tagged [] with general=True belongs to no tab (login, glossary, troubleshooting...):
those are answerable by nobody -> scope "off_topic" per the agreed flow.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.scope.tabs import TabCatalog  # noqa: E402

MANUAL = ROOT / "Ability_CRM_User_Manual.md"
OUT = ROOT / "app" / "data" / "manual" / "section_tabs.json"

# ## sections that carry no tab at all: every question inside them is "general".
GENERAL_SECTIONS = re.compile(
    r"^(Table of Contents|1\.|2\.|3\.|19\.|20\.|21\.|22\.|23\.|24\.)"
)

# Default tab(s) for a ## section: used when a question has no explicit entry below.
SECTION_DEFAULTS: dict[str, list[str]] = {
    "8. Customers": ["Search Customer"],
    "9. Unit": ["Unit"],
    "17. Document Library": ["DocumentLibrary"],
    "18. Settings (System Configuration)": ["Settings"],
    # 14. Definition: generic how-tos that apply to every Definition tab alike.
    "14. Definition (Master Data)": [
        "Department", "ERP Codes", "Invoice Types", "Location", "Location Type",
        "Positions", "Rental Companies", "Sister Companies", "Unit Block Categories",
    ],
}

# Questions whose flow NEEDS every tagged tab (e.g. creating a ticket needs Add Ticket even when
# started from the customer page). Everything else uses "any": one of its tabs is enough.
REQUIRE_ALL = {
    "How do I create a ticket from a customer's page?",
    "How do I create a ticket for a tenant?",
}

# Explicit tag per question (the hand-reviewed part). Keys must match the ### text exactly.
QUESTION_TABS: dict[str, list[str]] = {
    # 4. Complaints & Suggestions
    "How do I file a new complaint?": ["Add Complaint"],
    "How do I search for a complaint?": ["Search Complaint"],
    "How do I view a complaint's attachments from the search list?": ["Search Complaint"],
    "How do I open a complaint's details?": ["Search Complaint"],
    "How do I add a response to a complaint?": ["Search Complaint"],
    "How do I change a complaint's status (e.g. mark it Resolved)?": ["Search Complaint"],
    "How do I attach a document to a complaint?": ["Search Complaint"],
    # 5. Dashboard (tab names in the DB: Complaints / Statistics / Tickets)
    "Where do I see all open (live) complaints?": ["Complaints"],
    "Where do I see live tickets and their SLA status?": ["Tickets"],
    "How do I view statistics charts?": ["Statistics"],
    # 6. Tickets (details pages are reached from Search Tickets)
    "How do I create a new ticket?": ["Add Ticket"],
    "How do I search for tickets?": ["Search Tickets"],
    "What do the Status, SLA, Delayed and Urgent icons mean?": ["Search Tickets"],
    "How do I edit a ticket?": ["Search Tickets"],
    "How do I change a ticket's status?": ["Search Tickets"],
    "How do I add a comment to a ticket?": ["Search Tickets"],
    "How do I attach documents to a ticket?": ["Search Tickets"],
    "How do I print a ticket?": ["Search Tickets"],
    "How do I create a CTS record?": ["Add CTS"],
    "How do I search CTS records?": ["Search CTS"],
    # 7. Inquiries
    "How do I log a customer inquiry?": ["Add Inquiry"],
    "How do I search inquiries?": ["Search Inquiry"],
    # 8. Customers - section default, except:
    "How do I create a ticket from a customer's page?": ["Search Customer", "Add Ticket"],
    # 10. Services
    "How do I add a new service?": ["Add Service"],
    "How do I find, edit, activate or delete a service?": ["Service Search"],
    # 11. Rental (details pages are reached from Search Rentals)
    "How do I add a rental reservation?": ["Add Rental"],
    "How do I review a rental request (accept or reject)?": ["Rental Requests"],
    "How do I edit a rental request before accepting it?": ["Rental Requests"],
    "How do I search rentals?": ["Search Rentals"],
    "What is on a rental's details page?": ["Search Rentals"],
    "How do I edit a rental's details?": ["Search Rentals"],
    "How do I extend a rental (Change Reservation)?": ["Search Rentals"],
    "How do I issue an invoice on a rental?": ["Search Rentals"],
    "How do I check a tenant in?": ["Search Rentals"],
    "How do I check a tenant out?": ["Search Rentals"],
    "How do I terminate a rental early?": ["Search Rentals"],
    "How do I print the rental contract (Print RC)?": ["Search Rentals"],
    "How do I create a ticket for a tenant?": ["Search Rentals", "Add Ticket"],
    "What is the life cycle of a rental?": ["Add Rental", "Search Rentals"],
    "How do I upload broker rentals in bulk (Broker Attachments)?": ["Broker Attachments"],
    # 12. Invoices
    "How do I create a manual invoice?": ["Add Invoice"],
    "How do I search for an invoice?": ["Search Invoices"],
    "What is on the invoice details page?": ["Search Invoices"],
    "How do I collect payment for a pending invoice?": ["Search Invoices"],
    "How do I request an invoice void?": ["Search Invoices"],
    "How do I void an invoice directly?": ["Search Invoices"],
    "How do I review my End of Day?": ["End Of Day"],
    "How do I review the Full End of Day for all employees?": ["Full End Of Day"],
    # 13. Reports (one question per report tab)
    "How do I run the Daily Invoices report?": ["Daily Invoices"],
    "How do I run the Departmental Services report?": ["Department Service End Of Day Report"],
    "How do I run the End Of Day report for a period?": ["End Of Day Report"],
    # 14. Definition - section default (all 9 tabs), except the location-specific one:
    "How do I add a location or sub-location?": ["Location"],
    # 15. Users
    "How do I add a new user?": ["Add User"],
    "How do I find, edit or deactivate a user?": ["Manage Users"],
    "How do I send a password reset email to a user?": ["Manage Users"],
    # 16. Roles
    "How do I create a role and assign permissions?": ["Add Role"],
    "How do I edit or delete a role?": ["Manage Roles"],
    "Which modules and permissions can a role have?": ["Add Role", "Manage Roles"],
    "How do I give someone read-only access?": ["Add Role", "Manage Roles"],
    "Why can't a user see a menu entry or a button?": ["Manage Roles"],
}


def parse_manual() -> list[dict]:
    section = None
    general = False
    rows: list[dict] = []
    for n, line in enumerate(MANUAL.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            section = line[3:].strip()
            general = bool(GENERAL_SECTIONS.match(section))
        elif line.startswith("### ") and section:
            q = line[4:].strip()
            if general:
                tabs: list[str] = []
            elif q in QUESTION_TABS:
                tabs = QUESTION_TABS[q]
            elif section in SECTION_DEFAULTS:
                tabs = SECTION_DEFAULTS[section]
            else:
                raise SystemExit(f"UNTAGGED question (line {n}): {q!r} in section {section!r}")
            rows.append({
                "section": section, "question": q, "line": n, "general": general, "tabs": tabs,
                "require": "all" if q in REQUIRE_ALL else "any",
            })
    return rows


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    catalog = TabCatalog.from_settings(get_settings())
    valid = {t.name_en for t in catalog.tabs}
    rows = parse_manual()

    bad = [(r["question"], t) for r in rows for t in r["tabs"] if t not in valid]
    if bad:
        raise SystemExit(f"tags not in the 54-tab catalog: {bad}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    covered: dict[str, int] = {}
    for r in rows:
        for t in r["tabs"]:
            covered[t] = covered.get(t, 0) + 1
    print(f"{len(rows)} questions tagged -> {OUT.relative_to(ROOT)}\n")
    cur = None
    for r in rows:
        if r["section"] != cur:
            cur = r["section"]
            print(f"## {cur}")
        tag = "general" if r["general"] else ", ".join(r["tabs"])
        print(f"   {r['question']:70} -> {tag}")
    uncovered = sorted(valid - set(covered))
    print(f"\ntabs with manual questions: {len(covered)}/54")
    print(f"tabs WITHOUT a manual question (vector-DB fallback in part B): {uncovered}")


if __name__ == "__main__":
    main()
