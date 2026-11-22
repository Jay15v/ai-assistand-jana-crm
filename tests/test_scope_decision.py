"""Step 2 units: tab descriptions (part B) and the LLM scope decision (part C), with a fake LLM."""

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.features.agent.repositories.tabs import TabCatalog
from app.features.agent.services.scope import (
    ScopeDecision,
    ScopeDecisionError,
    build_descriptions,
    decide_scope,
    format_tab_list,
)
from tests.conftest import FakeLLM


@pytest.fixture(scope="module")
def catalog() -> TabCatalog:
    return TabCatalog.from_settings(get_settings())


@pytest.fixture(scope="module")
def descriptions(catalog) -> dict[str, str]:
    return build_descriptions(catalog)


def by_name(catalog, name):
    return next(t for t in catalog.tabs if t.name_en == name)


# --- part B: descriptions --------------------------------------------------------------------

def test_every_tab_has_a_description(catalog, descriptions):
    assert set(descriptions) == {t.doc_id for t in catalog.tabs}
    assert all(d.strip() for d in descriptions.values())

def test_manual_questions_describe_what_the_tab_does(catalog, descriptions):
    d = descriptions[by_name(catalog, "Search Invoices").doc_id]
    assert "void an invoice directly" in d  # from the manual, not the crawl
    assert "collect payment" in d

def test_tab_without_manual_section_falls_back_to_its_name(catalog, descriptions):
    # Notifications is the only tab with no manual section yet: bare name, nothing invented.
    assert descriptions[by_name(catalog, "Notifications").doc_id] == "Notifications"

def test_require_all_flow_names_the_other_tab(catalog, descriptions):
    d = descriptions[by_name(catalog, "Search Customer").doc_id]
    assert "create a ticket from a customer's page (also requires: 'Add Ticket')" in d

def test_format_tab_list(catalog, descriptions):
    line = format_tab_list([by_name(catalog, "Add Ticket")], descriptions)
    assert line.startswith("- Tickets > Add Ticket (إضافة تذكرة):")
    assert format_tab_list([], descriptions) == "(none)"


# --- part C: the decision --------------------------------------------------------------------

def tabs_split(catalog):
    allowed = [by_name(catalog, "Search Tickets"), by_name(catalog, "Search Complaint")]
    ids = {t.doc_id for t in allowed}
    return allowed, [t for t in catalog.tabs if t.doc_id not in ids]

def test_decision_passes_through_and_prompt_has_both_lists(catalog, descriptions):
    allowed, not_allowed = tabs_split(catalog)
    fake = FakeLLM(ScopeDecision(decision="allowed", reason="ticket search"))
    d = decide_scope(fake, "how do I find a ticket?", allowed, not_allowed, descriptions)
    assert d.decision == "allowed"
    user_prompt = fake.calls[0][1][1]
    allowed_part, rest = user_prompt.split("NOT-ALLOWED tabs", 1)
    assert "Search Tickets" in allowed_part and "Search Invoices" not in allowed_part
    assert "Search Invoices" in rest
    assert "how do I find a ticket?" in rest

def test_llm_exception_fails_closed(catalog, descriptions):
    allowed, not_allowed = tabs_split(catalog)
    with pytest.raises(ScopeDecisionError):
        decide_scope(FakeLLM(exc=TimeoutError("slow")), "q", allowed, not_allowed, descriptions)

def test_llm_returning_nothing_fails_closed(catalog, descriptions):
    allowed, not_allowed = tabs_split(catalog)
    with pytest.raises(ScopeDecisionError):
        decide_scope(FakeLLM(result=None), "q", allowed, not_allowed, descriptions)

def test_partial_must_carry_both_parts():
    with pytest.raises(ValidationError):
        ScopeDecision(decision="partial", allowed_question="only one part")

def test_non_partial_drops_stray_parts():
    d = ScopeDecision(decision="allowed", allowed_question="noise", not_allowed_question="noise")
    assert d.allowed_question is None and d.not_allowed_question is None
