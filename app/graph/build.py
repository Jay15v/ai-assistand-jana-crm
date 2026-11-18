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
from app.graph.history import make_compact_history, record_turn
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
    return "error_reply" if state.get("error") else "record_turn"


def _serde():
    """Serializer that explicitly allows the custom types living in ChatState, so checkpointing
    keeps working when LangGraph starts blocking unregistered types."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    return JsonPlusSerializer(allowed_msgpack_modules=[
        ("app.models.menu", "MenuResponse"),
        ("app.models.menu", "MenuGroup"),
        ("app.models.menu", "MenuItem"),
        ("app.models.menu", "MenuPrivilege"),
        ("app.scope.tabs", "Tab"),
        ("app.manual.chunks", "ManualChunk"),
    ])


def get_checkpointer(settings: Settings | None = None):
    """Postgres when DATABASE_URL is set (production); otherwise in-memory (dev: history is
    kept per session while the process runs, lost on restart)."""
    settings = settings or get_settings()
    if settings.database_url:
        from langgraph.checkpoint.postgres import PostgresSaver

        saver_cm = PostgresSaver.from_conn_string(settings.database_url)
        saver = saver_cm.__enter__()  # kept open for the process lifetime
        saver.setup()
        saver.serde = _serde()
        return saver
    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver(serde=_serde())


def build_graph(
    catalog: TabCatalog | None = None,
    settings: Settings | None = None,
    llm=None,
    index=None,
    checkpointer=None,
):
    """Build and compile the graph. Heavy pieces load once (catalog, descriptions); the LLM and
    the manual index are created lazily on first use. Tests inject fakes for all of them.

    `checkpointer` turns on chat memory: invoke with config={"configurable": {"thread_id":
    session_id}} and `history`/`summary` persist per session (use get_checkpointer(settings)
    for the Postgres-or-memory default). Without it the graph stays stateless, as before."""
    settings = settings or get_settings()
    if catalog is None:
        catalog = TabCatalog.from_settings(settings)
    descriptions = build_descriptions(catalog)
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
    graph.add_node("record_turn", record_turn)
    graph.add_node("compact_history", make_compact_history(get_llm, settings))

    graph.add_edge(START, "resolve_tabs")
    graph.add_conditional_edges("resolve_tabs", route_after_tabs, ["error_reply", "check_scope"])
    graph.add_conditional_edges(
        "check_scope",
        route_after_scope,
        ["error_reply", "not_allowed_reply", "off_topic_reply", "retrieve_section"],
    )
    graph.add_conditional_edges("retrieve_section", route_after_retrieve, ["generate_steps", "no_docs_reply"])
    graph.add_conditional_edges("generate_steps", route_after_generate, ["error_reply", "record_turn"])
    # Every reply path ends in record_turn (it only records answered turns), then the compact
    # gate squeezes old turns into the summary once the history is long.
    for node in ("error_reply", "not_allowed_reply", "off_topic_reply", "no_docs_reply"):
        graph.add_edge(node, "record_turn")
    graph.add_conditional_edges(
        "record_turn",
        lambda state: "compact_history"
        if len(state.get("history") or []) > settings.compact_after_turns
        else END,
        ["compact_history", END],
    )
    graph.add_edge("compact_history", END)
    return graph.compile(checkpointer=checkpointer)
