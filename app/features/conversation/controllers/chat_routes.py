"""HTTP endpoints of the conversation feature. No logic here: parse, call the service, return."""

from fastapi import APIRouter, Depends, Request

from app.features.agent.schemas import ChatRequest, ChatResponse
from app.features.conversation.services.chat_service import ChatService

router = APIRouter(prefix="/ai", tags=["conversation"])


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


# Plain `def` on purpose: the graph call blocks, so FastAPI runs it in its thread pool
# instead of freezing the event loop for every other request.
@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, service: ChatService = Depends(get_chat_service)) -> ChatResponse:
    return service.send(body)
