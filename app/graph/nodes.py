"""Graph nodes. Each node takes the state and returns a dict with only the fields it sets.

Factories (make_*) receive their heavy dependencies (tab catalog, LLM, descriptions) once, when
the graph is built - nothing is loaded per message.
"""

import logging
from collections.abc import Callable

from app.graph.state import ChatState
from app.scope.decide import ScopeDecisionError, decide_scope
from app.scope.tabs import MenuUnavailableError, TabCatalog, resolve_user_tabs

log = logging.getLogger("crm_ai.graph")

ERROR_MESSAGES = {
    "en": "The CRM assistant is temporarily unavailable. Please try again in a few minutes.",
    "ar": "المساعد غير متاح حاليًا. برجاء المحاولة مرة أخرى بعد قليل.",
}
NOT_ALLOWED_MESSAGES = {
    "en": "This feature isn't available under your current permissions. "
    "Please contact your system administrator if you need access.",
    "ar": "هذه الخاصية غير متاحة ضمن صلاحياتك الحالية. برجاء التواصل مع مسؤول النظام إذا كنت تحتاج إليها.",
}
OFF_TOPIC_MESSAGES = {
    "en": "I can help you with how to use the CRM screens. What would you like to do?",
    "ar": "أقدر أساعدك في طريقة استخدام شاشات النظام. تحب تعمل إيه؟",
}


def make_resolve_tabs(catalog: TabCatalog) -> Callable[[ChatState], dict]:
    """Step 1 node: the user's menu JSON -> allowed / not-allowed tabs (static, no AI)."""

    def resolve_tabs(state: ChatState) -> dict:
        try:
            user = resolve_user_tabs(state["menu"], catalog)
        except MenuUnavailableError as exc:
            log.warning("menu unusable: %s", exc)
            return {"error": str(exc)}
        return {
            "allowed_tabs": user.allowed,
            "not_allowed_tabs": user.not_allowed,
            "unknown_tabs": user.unknown_names,
            "error": None,
        }

    return resolve_tabs


def make_check_scope(get_llm: Callable[[], object], descriptions: dict[str, str]) -> Callable[[ChatState], dict]:
    """Step 2 node: the LLM decides by meaning whether the question is within the user's tabs.

    `get_llm` is called lazily on first use, so building the graph needs no API key (tests inject
    a fake). Fail closed: an LLM failure sets `error`, which routes to error_reply.
    """
    cache: list = []

    def check_scope(state: ChatState) -> dict:
        if not cache:
            cache.append(get_llm())
        try:
            d = decide_scope(
                cache[0],
                state["message"],
                state["allowed_tabs"],
                state["not_allowed_tabs"],
                descriptions,
            )
        except ScopeDecisionError as exc:
            log.error("%s", exc)
            return {"error": str(exc)}
        return {
            "scope": d.decision,
            "allowed_question": d.allowed_question,
            "not_allowed_question": d.not_allowed_question,
            "scope_reason": d.reason,
        }

    return check_scope


def error_reply(state: ChatState) -> dict:
    """Fixed bilingual message when the menu or the scope LLM failed (fail closed, no LLM)."""
    return {"answer": ERROR_MESSAGES[state["ui_lang"]]}


def not_allowed_reply(state: ChatState) -> dict:
    return {"answer": NOT_ALLOWED_MESSAGES[state["ui_lang"]]}


def off_topic_reply(state: ChatState) -> dict:
    return {"answer": OFF_TOPIC_MESSAGES[state["ui_lang"]]}
