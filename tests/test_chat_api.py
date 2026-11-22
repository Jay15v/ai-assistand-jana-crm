"""POST /chat through the real FastAPI app, routes and service. The graph is real too; only the
LLM and the manual index are fakes, so there is no API key and no network."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import Settings, get_settings
from app.features.agent.repositories.manual import load_chunks
from app.features.agent.repositories.tabs import TabCatalog
from app.features.agent.services.graph import build_graph
from app.features.agent.services.scope import ScopeDecision
from app.features.conversation.services.chat_service import ChatService
from app.main import create_app
from tests.conftest import FakeIndex, FakeLLM

FIXTURES = Path(__file__).parent / "fixtures"
MENU = json.loads((FIXTURES / "menu_admin.json").read_text(encoding="utf-8"))
NO_TRACING = Settings(_env_file=None, langfuse_public_key=None, langfuse_secret_key=None)


@pytest.fixture(scope="module")
def catalog():
    return TabCatalog.from_settings(get_settings())


@pytest.fixture(scope="module")
def ticket_chunk():
    return next(c for c in load_chunks() if c.question_en == "How do I search for tickets?")


def client_for(catalog, chunk, llm) -> TestClient:
    graph = build_graph(catalog, llm=llm, index=FakeIndex(hits=[(chunk, 0.9)]), checkpointer=InMemorySaver())
    return TestClient(create_app(ChatService(graph, NO_TRACING)))


def body(**overrides) -> dict:
    base = {"user_id": "u1", "session_id": "s1", "message": "how do I search for tickets?",
            "ui_lang": "en", "menu": MENU}
    return {**base, **overrides}


def allowed_llm() -> FakeLLM:
    return FakeLLM(ScopeDecision(decision="allowed", reason="t", standalone_question="How do I search for tickets?"))


def test_chat_returns_answer_scope_and_session_only(catalog, ticket_chunk):
    with client_for(catalog, ticket_chunk, allowed_llm()) as client:
        res = client.post("/chat", json=body())
    assert res.status_code == 200
    assert res.json() == {"session_id": "s1", "answer": "FAKE STEPS", "scope": "allowed"}


def test_not_allowed_question_is_refused_without_generating(catalog, ticket_chunk):
    llm = FakeLLM(ScopeDecision(decision="not_allowed", reason="t"))
    with client_for(catalog, ticket_chunk, llm) as client:
        res = client.post("/chat", json=body())
    assert res.status_code == 200
    assert res.json()["scope"] == "not_allowed"
    assert res.json()["answer"]  # the refusal text
    assert llm.answer_calls == []  # the answer LLM never ran


def test_failed_scope_llm_gives_error_scope_not_a_500(catalog, ticket_chunk):
    llm = FakeLLM(exc=RuntimeError("gemini down"))
    with client_for(catalog, ticket_chunk, llm) as client:
        res = client.post("/chat", json=body())
    assert res.status_code == 200
    assert res.json()["scope"] == "error"
    assert res.json()["answer"]  # the "temporarily unavailable" text


def test_same_session_remembers_the_previous_turn(catalog, ticket_chunk):
    llm = allowed_llm()
    with client_for(catalog, ticket_chunk, llm) as client:
        client.post("/chat", json=body())
        client.post("/chat", json=body(message="and how do I print one?"))
    second_scope_prompt = str(llm.calls[1])
    assert "how do I search for tickets?" in second_scope_prompt
    assert "FAKE STEPS" in second_scope_prompt


def test_other_session_does_not_see_that_history(catalog, ticket_chunk):
    llm = allowed_llm()
    with client_for(catalog, ticket_chunk, llm) as client:
        client.post("/chat", json=body())
        client.post("/chat", json=body(session_id="s2", message="and how do I print one?"))
    assert "FAKE STEPS" not in str(llm.calls[1])


def test_another_user_with_the_same_session_id_does_not_see_that_history(catalog, ticket_chunk):
    llm = allowed_llm()
    with client_for(catalog, ticket_chunk, llm) as client:
        client.post("/chat", json=body(user_id="alice"))
        client.post("/chat", json=body(user_id="bob", message="and how do I print one?"))
    assert "FAKE STEPS" not in str(llm.calls[1])
    assert "Conversation so far" not in str(llm.calls[1])


def test_user_and_session_cannot_be_combined_into_someone_elses_key(catalog, ticket_chunk):
    llm = allowed_llm()
    with client_for(catalog, ticket_chunk, llm) as client:
        client.post("/chat", json=body(user_id="a", session_id="b:c"))
        client.post("/chat", json=body(user_id="a:b", session_id="c", message="and how do I print one?"))
    assert "FAKE STEPS" not in str(llm.calls[1])


def test_locale_form_of_ui_lang_is_accepted(catalog, ticket_chunk):
    with client_for(catalog, ticket_chunk, allowed_llm()) as client:
        res = client.post("/chat", json=body(ui_lang="ar-EG"))
    assert res.status_code == 200


@pytest.mark.parametrize("bad", [
    {"ui_lang": "fr"},
    {"message": ""},
    {"message": "x" * 2001},
    {"session_id": ""},
    {"user_id": ""},
])
def test_invalid_request_is_rejected_with_422(catalog, ticket_chunk, bad):
    llm = allowed_llm()
    with client_for(catalog, ticket_chunk, llm) as client:
        res = client.post("/chat", json=body(**bad))
    assert res.status_code == 422
    assert llm.calls == []  # nothing reached the graph


def test_missing_menu_is_rejected_with_422(catalog, ticket_chunk):
    payload = body()
    del payload["menu"]
    with client_for(catalog, ticket_chunk, allowed_llm()) as client:
        res = client.post("/chat", json=payload)
    assert res.status_code == 422
