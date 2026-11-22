"""HTTP endpoints of the agent feature. No logic here: parse, call the service, return."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.features.agent.repositories.tabs import MenuUnavailableError
from app.features.agent.schemas import ScopeRequest
from app.features.agent.services.scope import ScopeDecision, ScopeDecisionError, ScopeService

log = logging.getLogger("crm_ai.agent")

router = APIRouter(prefix="/agent", tags=["agent"])


def get_scope_service(request: Request) -> ScopeService:
    return request.app.state.scope_service


# Plain `def` on purpose: the LLM call blocks, so FastAPI runs it in its thread pool.
@router.post("/scope", response_model=ScopeDecision)
def scope(body: ScopeRequest, service: ScopeService = Depends(get_scope_service)) -> ScopeDecision:
    """Run only the scope decision for one message: no memory, no retrieval, no answer."""
    try:
        return service.check(body.message, body.menu)
    except MenuUnavailableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ScopeDecisionError as exc:
        log.error("%s", exc)  # the detail stays in the logs; the caller gets a generic message
        raise HTTPException(status_code=503, detail="The scope decision is temporarily unavailable.") from exc
