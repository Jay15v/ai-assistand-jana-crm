"""The LangGraph checkpointer: where the per-session chat memory (history + summary) is stored."""

from app.core.config import Settings, get_settings


def _serde():
    """Serializer that explicitly allows the custom types living in ChatState, so checkpointing
    keeps working when LangGraph starts blocking unregistered types."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    return JsonPlusSerializer(allowed_msgpack_modules=[
        ("app.features.agent.schemas", "MenuResponse"),
        ("app.features.agent.schemas", "MenuGroup"),
        ("app.features.agent.schemas", "MenuItem"),
        ("app.features.agent.schemas", "MenuPrivilege"),
        ("app.features.agent.repositories.tabs", "Tab"),
        ("app.features.agent.repositories.manual", "ManualChunk"),
    ])


def get_checkpointer(settings: Settings | None = None, pool=None):
    """Postgres when DATABASE_URL is set (production); otherwise in-memory (dev: history is
    kept per session while the process runs, lost on restart).

    The app passes its shared pool. Scripts pass nothing and get a pool of their own.
    setup() creates LangGraph's tables (in settings.db_schema) on first start, then only
    runs LangGraph's own migrations when its version needs them."""
    settings = settings or get_settings()
    if pool is not None or settings.database_url:
        from langgraph.checkpoint.postgres import PostgresSaver

        from app.core.database import open_pool

        saver = PostgresSaver(pool if pool is not None else open_pool(settings), serde=_serde())
        saver.setup()
        return saver
    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver(serde=_serde())
