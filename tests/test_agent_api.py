"""POST /agent/scope through the real FastAPI app, route and ScopeService. Only the LLM is a
fake, so there is no API key and no network."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.features.agent.repositories.tabs import TabCatalog
from app.features.agent.services.scope import ScopeDecision, ScopeService
from app.main import create_app
from tests.conftest import FakeLLM

FIXTURES = Path(__file__).parent / "fixtures"


def menu(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def catalog():
    return TabCatalog.from_settings(get_settings())


def client_for(catalog, llm) -> TestClient:
    return TestClient(create_app(scope_service=ScopeService(catalog, lambda: llm)))


def body(**overrides) -> dict:
    return {"message": "how do I void an invoice?", "menu": menu("menu_readonly_role.json"), **overrides}


def test_scope_returns_the_decision(catalog):
    llm = FakeLLM(ScopeDecision(decision="not_allowed", reason="invoices are not in this role"))
    with client_for(catalog, llm) as client:
        res = client.post("/agent/scope", json=body())
    assert res.status_code == 200
    assert res.json() == {
        "checks": [],  # the scope model's per-action reasoning, kept in the reply for tracing
        "reason": "invoices are not in this role",
        "decision": "not_allowed",
        "standalone_question": None,
        "allowed_question": None,
        "not_allowed_question": None,
    }


def test_partial_decision_carries_both_parts(catalog):
    llm = FakeLLM(ScopeDecision(decision="partial", allowed_question="find a ticket",
                                not_allowed_question="create a ticket"))
    with client_for(catalog, llm) as client:
        res = client.post("/agent/scope", json=body(message="find a ticket then create one"))
    assert res.json()["allowed_question"] == "find a ticket"
    assert res.json()["not_allowed_question"] == "create a ticket"


def test_prompt_lists_the_tabs_of_the_menu_that_was_sent(catalog):
    """The menu in the request, not anything cached, decides the allowed / not-allowed lists."""
    llm = FakeLLM(ScopeDecision(decision="allowed", standalone_question="q"))
    with client_for(catalog, llm) as client:
        client.post("/agent/scope", json=body(menu=menu("menu_readonly_role.json")))
        client.post("/agent/scope", json=body(menu=menu("menu_admin.json")))
    readonly_prompt, admin_prompt = (call[1][1] for call in llm.calls)
    allowed_part = lambda prompt: prompt.split("NOT-ALLOWED tabs")[0]  # noqa: E731
    assert "Search Invoices" not in allowed_part(readonly_prompt)
    assert "Search Invoices" in allowed_part(admin_prompt)


def test_scope_only_never_calls_the_answer_llm(catalog):
    llm = FakeLLM(ScopeDecision(decision="allowed", standalone_question="q"))
    with client_for(catalog, llm) as client:
        client.post("/agent/scope", json=body())
    assert len(llm.calls) == 1
    assert llm.answer_calls == []


def test_llm_failure_is_503_without_leaking_the_cause(catalog):
    llm = FakeLLM(exc=RuntimeError("secret upstream detail"))
    with client_for(catalog, llm) as client:
        res = client.post("/agent/scope", json=body())
    assert res.status_code == 503
    assert "secret upstream detail" not in res.text


@pytest.mark.parametrize("flag", ["success", "is_maintenance"])
def test_unusable_menu_is_422_and_the_llm_is_not_called(catalog, flag):
    bad_menu = menu("menu_readonly_role.json")
    bad_menu[flag] = flag == "is_maintenance"  # success=False, or is_maintenance=True
    llm = FakeLLM(ScopeDecision(decision="allowed", standalone_question="q"))
    with client_for(catalog, llm) as client:
        res = client.post("/agent/scope", json=body(menu=bad_menu))
    assert res.status_code == 422
    assert llm.calls == []


@pytest.mark.parametrize("bad", [{"message": ""}, {"message": "x" * 2001}])
def test_invalid_message_is_422(catalog, bad):
    llm = FakeLLM(ScopeDecision(decision="allowed", standalone_question="q"))
    with client_for(catalog, llm) as client:
        res = client.post("/agent/scope", json=body(**bad))
    assert res.status_code == 422
    assert llm.calls == []
