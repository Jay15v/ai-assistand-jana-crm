"""Wires the chatbot graph.

Current graph (steps 1 + 2; step 3 - the answer from the manual - will replace the END after
"allowed" / "partial"):

    START -> resolve_tabs -+- menu failed --------------------------> error_reply ------> END
                           +- OK -> check_scope -+- off_topic ------> off_topic_reply --> END
                                                 +- not_allowed ----> not_allowed_reply > END
                                                 +- LLM failed -----> error_reply ------> END
                                                 +- allowed/partial -----------------------> END
"""

from langgraph.graph import END, START, StateGraph

from app.config import Settings, get_settings
from app.graph.nodes import (
    error_reply,
    make_check_scope,
    make_resolve_tabs,
    not_allowed_reply,
    off_topic_reply,
)
from app.graph.state import ChatState
from app.llm import get_chat_model
from app.scope.descriptions import build_descriptions
from app.scope.tabs import TabCatalog


def route_after_tabs(state: ChatState) -> str:
    return "error_reply" if state.get("error") else "check_scope"


def route_after_scope(state: ChatState) -> str:
    if state.get("error"):
        return "error_reply"
    scope = state["scope"]
    if scope == "off_topic":
        return "off_topic_reply"
    if scope == "not_allowed":
        return "not_allowed_reply"
    return END  # "allowed" / "partial": step 3 (answer from the manual) continues here later


def build_graph(catalog: TabCatalog | None = None, settings: Settings | None = None, llm=None):
    """Build and compile the graph.

    Heavy pieces load once here (catalog, descriptions); the LLM is created lazily on the first
    message. Tests inject `catalog` and a fake `llm`.
    """
    settings = settings or get_settings()
    if catalog is None:
        catalog = TabCatalog.from_settings(settings)
    descriptions = build_descriptions(catalog, settings)
    get_llm = (lambda: llm) if llm is not None else (lambda: get_chat_model(settings))

    graph = StateGraph(ChatState)
    graph.add_node("resolve_tabs", make_resolve_tabs(catalog))
    graph.add_node("check_scope", make_check_scope(get_llm, descriptions))
    graph.add_node("error_reply", error_reply)
    graph.add_node("not_allowed_reply", not_allowed_reply)
    graph.add_node("off_topic_reply", off_topic_reply)

    graph.add_edge(START, "resolve_tabs")
    graph.add_conditional_edges("resolve_tabs", route_after_tabs, ["error_reply", "check_scope"])
    graph.add_conditional_edges(
        "check_scope", route_after_scope, ["error_reply", "not_allowed_reply", "off_topic_reply", END]
    )
    graph.add_edge("error_reply", END)
    graph.add_edge("not_allowed_reply", END)
    graph.add_edge("off_topic_reply", END)
    return graph.compile()
