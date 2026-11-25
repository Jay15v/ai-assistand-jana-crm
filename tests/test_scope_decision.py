"""Step 2 units: tab descriptions (part B) and the LLM scope decision (part C), with a fake LLM."""

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.features.agent.repositories.tabs import TabCatalog
from app.features.agent.services.scope import (
    ActionCheck,
    ScopeDecision,
    ScopeDecisionError,
    apply_checks,
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


# --- apply_checks: code re-checks the model's tab look-ups (fail closed, never loosens) -------

def check(question, tab, found_in="ALLOWED"):
    return ActionCheck(question=question, tab=tab, found_in=found_in)


def test_allowed_with_a_blocked_tab_is_corrected_to_partial(catalog):
    allowed, not_allowed = tabs_split(catalog)
    d = ScopeDecision(  # the model looked up 'Add Complaint' wrongly and said allowed
        checks=[check("How do I search for tickets?", "Search Tickets"),
                check("How do I add a complaint?", "Add Complaint")],
        reason="r", decision="allowed", standalone_question="both")
    out = apply_checks(d, allowed, not_allowed)
    assert out.decision == "partial"
    assert out.allowed_question == "How do I search for tickets?"
    assert out.not_allowed_question == "How do I add a complaint?"
    assert "[corrected" in out.reason

def test_allowed_with_only_blocked_tabs_is_corrected_to_not_allowed(catalog):
    allowed, not_allowed = tabs_split(catalog)
    d = ScopeDecision(checks=[check("How do I void an invoice?", "Search Invoices")],
                      reason="r", decision="allowed", standalone_question="q")
    out = apply_checks(d, allowed, not_allowed)
    assert out.decision == "not_allowed"

def test_model_tab_name_shapes_still_resolve(catalog):
    allowed, not_allowed = tabs_split(catalog)
    ar_name = by_name(catalog, "Add Complaint").name_ar
    for tab_text in ("Invoices > Search Invoices", "'Search Invoices'",
                     f"Add Complaint ({ar_name})", ar_name):
        d = ScopeDecision(checks=[check("q?", tab_text)], reason="r",
                          decision="allowed", standalone_question="q")
        assert apply_checks(d, allowed, not_allowed).decision == "not_allowed", tab_text

def test_never_loosens_a_restrictive_decision(catalog):
    allowed, not_allowed = tabs_split(catalog)
    # model said not_allowed (e.g. an "(also requires: ...)" flow) though the checked tab is allowed
    d = ScopeDecision(checks=[check("q?", "Search Tickets")], reason="r", decision="not_allowed")
    assert apply_checks(d, allowed, not_allowed) is d

def test_unknown_tab_name_is_left_to_the_model(catalog):
    allowed, not_allowed = tabs_split(catalog)
    d = ScopeDecision(checks=[check("q?", "Imaginary Tab"), check("q2?", "none")],
                      reason="r", decision="allowed", standalone_question="q")
    assert apply_checks(d, allowed, not_allowed) is d

def test_partial_with_all_tabs_blocked_is_corrected_to_not_allowed(catalog):
    allowed, not_allowed = tabs_split(catalog)
    d = ScopeDecision(checks=[check("a?", "Search Invoices"), check("b?", "Add Complaint")],
                      reason="r", decision="partial",
                      allowed_question="a?", not_allowed_question="b?")
    assert apply_checks(d, allowed, not_allowed).decision == "not_allowed"

def test_decide_scope_runs_the_check(catalog, descriptions):
    allowed, not_allowed = tabs_split(catalog)
    fake = FakeLLM(ScopeDecision(checks=[check("How do I add a complaint?", "Add Complaint")],
                                 reason="r", decision="allowed", standalone_question="q"))
    d = decide_scope(fake, "how do I add a complaint?", allowed, not_allowed, descriptions)
    assert d.decision == "not_allowed"  # corrected inside decide_scope, not only in the graph
