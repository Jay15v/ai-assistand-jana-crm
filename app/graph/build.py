"""Wires the chatbot graph (steps 1 + 2 + 3).

    START -> resolve_tabs -+- menu failed ------------------------> error_reply -------> END
                           +- OK -> check_scope -+- off_topic ----> off_topic_reply --> END
                                                 +- not_allowed --> not_allowed_reply > END
                                                 +- LLM failed ---> error_reply ------> END
                                                 +- allowed/partial -> retrieve_section
                                                        +- nothing eligible -> no_docs_reply -> END
                                                        +- found -> generate_steps ----> END
                                                                        +- LLM failed -> error_reply
"""

from langgraph.graph import END, START, StateGraph

from app.config import Settings, get_settings
from app.graph.nodes import (
    error_reply,
    make_check_scope,
    make_generate_steps,
    make_resolve_tabs,
    make_retrieve_section,
    no_docs_reply,
    not_allowed_reply,
    off_topic_reply,
)
from app.graph.state import ChatState
from app.llm import get_chat_model
from app.manual.index import ManualIndex
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
    return "retrieve_section"  # "allowed" / "partial"


def route_after_retrieve(state: ChatState) -> str:
    return "generate_steps" if state["sections"] else "no_docs_reply"


def route_after_generate(state: ChatState) -> str:
    return "error_reply" if state.get("error") else END


def build_graph(
    catalog: TabCatalog | None = None,
    settings: Settings | None = None,
    llm=None,
    index=None,
):
    """Build and compile the graph. Heavy pieces load once (catalog, descriptions); the LLM and
    the manual index are created lazily on first use. Tests inject fakes for all of them."""
    settings = settings or get_settings()
    if catalog is None:
        catalog = TabCatalog.from_settings(settings)
    descriptions = build_descriptions(catalog, settings)
    get_llm = (lambda: llm) if llm is not None else (lambda: get_chat_model(settings))
    get_index = (lambda: index) if index is not None else (lambda: ManualIndex(settings))

    graph = StateGraph(ChatState)
    graph.add_node("resolve_tabs", make_resolve_tabs(catalog))
    graph.add_node("check_scope", make_check_scope(get_llm, descriptions))
    graph.add_node("retrieve_section", make_retrieve_section(get_index))
    graph.add_node("generate_steps", make_generate_steps(get_llm))
    graph.add_node("error_reply", error_reply)
    graph.add_node("not_allowed_reply", not_allowed_reply)
    graph.add_node("off_topic_reply", off_topic_reply)
    graph.add_node("no_docs_reply", no_docs_reply)

    graph.add_edge(START, "resolve_tabs")
    graph.add_conditional_edges("resolve_tabs", route_after_tabs, ["error_reply", "check_scope"])
    graph.add_conditional_edges(
        "check_scope",
        route_after_scope,
        ["error_reply", "not_allowed_reply", "off_topic_reply", "retrieve_section"],
    )
    graph.add_conditional_edges("retrieve_section", route_after_retrieve, ["generate_steps", "no_docs_reply"])
    graph.add_conditional_edges("generate_steps", route_after_generate, ["error_reply", END])
    for node in ("error_reply", "not_allowed_reply", "off_topic_reply", "no_docs_reply"):
        graph.add_edge(node, END)
    return graph.compile()
