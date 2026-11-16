"""The LangGraph pipeline: steps 1 + 2 wired together (fake LLM - no API key, no network)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import get_settings
from app.graph import build as build_module
from app.graph.build import build_graph
from app.graph.nodes import (
    ERROR_MESSAGES,
    NO_DOCS_MESSAGES,
    NOT_ALLOWED_MESSAGES,
    OFF_TOPIC_MESSAGES,
    PARTIAL_NOTICES,
)
from app.graph.state import initial_state
from app.manual.chunks import load_chunks
from app.models.chat import ChatRequest
from app.scope.decide import ScopeDecision
from app.scope.tabs import TabCatalog
from tests.conftest import FakeIndex, FakeLLM

FIXTURES = Path(__file__).parent / "fixtures"


def menu_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def request(menu: dict, ui_lang: str = "en", message: str = "how do I add a ticket?") -> ChatRequest:
    return ChatRequest(user_id="u1", session_id="s1", message=message, ui_lang=ui_lang, menu=menu)


@pytest.fixture(scope="module")
def catalog():
    return TabCatalog.from_settings(get_settings())


@pytest.fixture(scope="module")
def ticket_chunk():
    return next(c for c in load_chunks() if c.question_en == "How do I search for tickets?")


@pytest.fixture
def fake_llm():
    return FakeLLM(ScopeDecision(decision="allowed", reason="test default"))


@pytest.fixture
def fake_index(ticket_chunk):
    return FakeIndex(hits=[(ticket_chunk, 0.9)])


@pytest.fixture
def graph(catalog, fake_llm, fake_index):
    return build_graph(catalog, llm=fake_llm, index=fake_index)


def run(graph, menu: dict, ui_lang: str = "en", message: str = "how do I add a ticket?") -> dict:
    return graph.invoke(initial_state(request(menu, ui_lang, message)))


# --- step 1 through the pipeline -------------------------------------------------------------

def test_admin_allowed_question_gets_an_answer(graph, fake_llm, fake_index):
    out = run(graph, menu_json("menu_admin.json"))
    assert len(out["allowed_tabs"]) == 54
    assert out["scope"] == "allowed"
    assert len(out["sections"]) == 1
    assert out["answer"] == "FAKE STEPS"  # retrieve -> generate ran
    assert len(fake_llm.calls) == 1  # scope
    assert len(fake_llm.answer_calls) == 1  # generate
    # retrieval was called with the raw message and THIS user's tab names
    query, allowed_names, _ = fake_index.searches[0]
    assert query == "how do I add a ticket?"
    assert "Search Invoices" in allowed_names  # admin has everything

def test_real_readonly_role_tabs(graph):
    out = run(graph, menu_json("menu_readonly_role.json"))
    assert len(out["allowed_tabs"]) == 5
    assert len(out["not_allowed_tabs"]) == 49

@pytest.mark.parametrize("ui_lang", ["en", "ar"])
@pytest.mark.parametrize("field, value", [("success", False), ("is_maintenance", True)])
def test_unusable_menu_goes_to_error_reply(graph, fake_llm, field, value, ui_lang):
    menu = menu_json("menu_readonly_role.json")
    menu[field] = value
    out = run(graph, menu, ui_lang)
    assert out["error"]
    assert out["answer"] == ERROR_MESSAGES[ui_lang]
    assert fake_llm.calls == []  # scope LLM never reached


# --- step 2 routing --------------------------------------------------------------------------

@pytest.mark.parametrize("ui_lang", ["en", "ar"])
def test_not_allowed_routes_to_fixed_reply(catalog, ui_lang):
    fake = FakeLLM(ScopeDecision(decision="not_allowed", reason="invoices not in tabs"))
    out = run(build_graph(catalog, llm=fake), menu_json("menu_readonly_role.json"), ui_lang,
              "how do I void an invoice?")
    assert out["scope"] == "not_allowed"
    assert out["answer"] == NOT_ALLOWED_MESSAGES[ui_lang]

@pytest.mark.parametrize("ui_lang", ["en", "ar"])
def test_off_topic_routes_to_fixed_reply(catalog, ui_lang):
    fake = FakeLLM(ScopeDecision(decision="off_topic", reason="small talk"))
    out = run(build_graph(catalog, llm=fake), menu_json("menu_readonly_role.json"), ui_lang, "hello!")
    assert out["answer"] == OFF_TOPIC_MESSAGES[ui_lang]

@pytest.mark.parametrize("ui_lang", ["en", "ar"])
def test_partial_answers_allowed_part_plus_fixed_notice(catalog, ticket_chunk, ui_lang):
    fake = FakeLLM(ScopeDecision(
        decision="partial",
        allowed_question="How do I search for a ticket?",
        not_allowed_question="How do I create a ticket?",
        reason="search allowed, add not",
    ))
    index = FakeIndex(hits=[(ticket_chunk, 0.9)])
    out = run(build_graph(catalog, llm=fake, index=index), menu_json("menu_readonly_role.json"),
              ui_lang, "find a ticket then create one")
    assert out["scope"] == "partial"
    # retrieval searched ONLY the allowed part - the blocked part never reaches the index
    assert index.searches[0][0] == "How do I search for a ticket?"
    # the answer is the steps + the code-appended notice naming the blocked part
    expected_notice = PARTIAL_NOTICES[ui_lang].format(blocked="How do I create a ticket?")
    assert out["answer"] == "FAKE STEPS" + expected_notice


@pytest.mark.parametrize("ui_lang", ["en", "ar"])
def test_no_eligible_section_gives_no_docs_reply(catalog, fake_llm, ui_lang):
    out = run(build_graph(catalog, llm=fake_llm, index=FakeIndex(hits=[])),
              menu_json("menu_readonly_role.json"), ui_lang)
    assert out["sections"] == []
    assert out["answer"] == NO_DOCS_MESSAGES[ui_lang]
    assert fake_llm.answer_calls == []  # generator never ran


@pytest.mark.parametrize("ui_lang", ["en", "ar"])
def test_answer_llm_failure_fails_closed(catalog, ticket_chunk, ui_lang):
    fake = FakeLLM(ScopeDecision(decision="allowed", reason="ok"),
                   answer_exc=TimeoutError("gemini down"))
    out = run(build_graph(catalog, llm=fake, index=FakeIndex(hits=[(ticket_chunk, 0.9)])),
              menu_json("menu_readonly_role.json"), ui_lang)
    assert out["error"]
    assert out["answer"] == ERROR_MESSAGES[ui_lang]

@pytest.mark.parametrize("ui_lang", ["en", "ar"])
def test_scope_llm_failure_fails_closed(catalog, ui_lang):
    fake = FakeLLM(exc=TimeoutError("gemini down"))
    out = run(build_graph(catalog, llm=fake), menu_json("menu_readonly_role.json"), ui_lang)
    assert out["error"]
    assert out["answer"] == ERROR_MESSAGES[ui_lang]  # never defaults to allowed

def test_scope_prompt_uses_this_users_split(catalog, fake_llm, graph):
    run(graph, menu_json("menu_readonly_role.json"), message="how do I void an invoice?")
    user_prompt = fake_llm.calls[0][1][1]
    allowed_part, rest = user_prompt.split("NOT-ALLOWED tabs", 1)
    assert "Search Tickets" in allowed_part
    assert "Search Invoices" in rest and "void an invoice" in rest


# --- language rules (unchanged from step 1) --------------------------------------------------

@pytest.mark.parametrize("ui_lang, expected", [("ar-EG", "ar"), ("AR", "ar"), ("en_US", "en")])
def test_locale_forms_reach_the_graph_normalized(graph, ui_lang, expected):
    menu = menu_json("menu_readonly_role.json")
    menu["is_maintenance"] = True
    out = run(graph, menu, ui_lang)
    assert out["ui_lang"] == expected
    assert out["answer"] == ERROR_MESSAGES[expected]

@pytest.mark.parametrize("bad", ["fr", "", "arabic"])
def test_unknown_ui_lang_never_reaches_the_graph(bad):
    with pytest.raises(ValidationError):
        request(menu_json("menu_admin.json"), ui_lang=bad)

def test_missing_ui_lang_or_menu_is_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(user_id="u1", session_id="s1", message="hi", menu=menu_json("menu_admin.json"))
    with pytest.raises(ValidationError):
        ChatRequest(user_id="u1", session_id="s1", message="hi", ui_lang="en")


def test_catalog_loaded_once(monkeypatch, fake_llm, fake_index):
    calls = []
    real = TabCatalog.from_settings

    def counting(settings):
        calls.append(1)
        return real(settings)

    monkeypatch.setattr(build_module.TabCatalog, "from_settings", staticmethod(counting))
    g = build_graph(llm=fake_llm, index=fake_index)
    for _ in range(3):
        run(g, menu_json("menu_limited.json"))
    assert len(calls) == 1
