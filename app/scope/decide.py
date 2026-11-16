"""Part C of the scope flow: the LLM decision (allowed / partial / not_allowed / off_topic).

Fail closed: any LLM failure (timeout, API error, malformed output) raises ScopeDecisionError.
The graph routes that to the error reply - it NEVER defaults to "allowed".
"""

import logging
import time
from typing import Literal

from pydantic import BaseModel, model_validator

from app.scope.prompts import SCOPE_SYSTEM_PROMPT, scope_user_prompt
from app.scope.tabs import Tab

log = logging.getLogger("crm_ai.scope")


class ScopeDecisionError(RuntimeError):
    """The scope LLM could not produce a usable decision."""


class ScopeDecision(BaseModel):
    # Field order matters: the LLM fills `reason` first, so it reasons BEFORE it decides.
    reason: str = ""  # for logs/debugging, never shown to the user
    decision: Literal["allowed", "partial", "not_allowed", "off_topic"]
    allowed_question: str | None = None  # partial only: the part the user may ask
    not_allowed_question: str | None = None  # partial only: the part outside their permissions

    @model_validator(mode="after")
    def _partial_needs_both_parts(self) -> "ScopeDecision":
        if self.decision == "partial" and not (self.allowed_question and self.not_allowed_question):
            raise ValueError("partial decision must carry both question parts")
        if self.decision != "partial":
            self.allowed_question = None
            self.not_allowed_question = None
        return self


def decide_scope(
    llm,
    question: str,
    allowed: list[Tab],
    not_allowed: list[Tab],
    descriptions: dict[str, str],
) -> ScopeDecision:
    t0 = time.perf_counter()
    messages = [
        ("system", SCOPE_SYSTEM_PROMPT),
        ("human", scope_user_prompt(question, allowed, not_allowed, descriptions)),
    ]
    try:
        decision = llm.with_structured_output(ScopeDecision).invoke(messages)
    except Exception as exc:  # noqa: BLE001 - fail closed on anything
        raise ScopeDecisionError(f"scope LLM failed: {exc}") from exc
    if not isinstance(decision, ScopeDecision):  # e.g. None when the model returns nothing usable
        raise ScopeDecisionError(f"scope LLM returned no decision: {decision!r}")
    log.info(
        "scope q=%r -> %s (%s) in %.0f ms",
        question, decision.decision, decision.reason, (time.perf_counter() - t0) * 1000,
    )
    return decision
