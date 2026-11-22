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
