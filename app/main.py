"""The FastAPI app. This is the only place objects get built and wired together.

    uvicorn app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import open_pool
from app.core.llm import get_chat_model
from app.core.tracing import flush
from app.features.agent.controllers.agent_routes import router as agent_router
from app.features.agent.repositories.tabs import TabCatalog
from app.features.agent.services.graph import build_graph
from app.features.agent.services.scope import ScopeService
from app.features.conversation.controllers.chat_routes import router as chat_router
from app.features.conversation.repositories.checkpointer import get_checkpointer
from app.features.conversation.repositories.history import BackgroundHistoryWriter, ChatHistoryRepository
from app.features.conversation.services.chat_service import ChatService


def create_app(chat_service: ChatService | None = None, scope_service: ScopeService | None = None) -> FastAPI:
    """Build the app. Production passes nothing and the real services are built at startup.
    Tests pass the service(s) they exercise, and nothing real is built."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pool = history = None
        if chat_service is None and scope_service is None:
            settings = get_settings()
            logging.basicConfig(level=settings.log_level)
            # One pool for the chat memory and the history tables; none without DATABASE_URL.
            pool = open_pool(settings) if settings.database_url else None
            # History rows are written in the background: the reply never waits for them.
            history = BackgroundHistoryWriter(ChatHistoryRepository(pool, settings.db_schema)) if pool else None
            # Built once: loading the tab catalog and descriptions per request would be slow.
            catalog = TabCatalog.from_settings(settings)
            graph = build_graph(catalog, settings, checkpointer=get_checkpointer(settings, pool))
            app.state.chat_service = ChatService(graph, settings, history)
            app.state.scope_service = ScopeService(catalog, lambda: get_chat_model(settings))
        else:
            app.state.chat_service = chat_service
            app.state.scope_service = scope_service
        yield
        flush()  # push any queued Langfuse events before the process exits
        if history is not None:
            history.close()  # write the turns still waiting, before their pool goes away
        if pool is not None:
            pool.close()

    app = FastAPI(title="Ability CRM assistant", lifespan=lifespan)

    @app.get("/ai/aws/health-check")
    def health_check() -> dict:
        """Liveness probe for the AWS load balancer and the Docker HEALTHCHECK."""
        return {"status": "ok"}

    app.include_router(chat_router)
    app.include_router(agent_router)
    return app


app = create_app()
