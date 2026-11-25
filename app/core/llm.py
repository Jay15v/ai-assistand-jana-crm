"""The one place that creates the Gemini chat model (LangChain), reused by every LLM node."""

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import Settings


def reply_text(reply) -> str:
    """The text of a plain (not structured) chat reply, stripped; "" when there is none.

    Gemini 2.x returns `content` as one string. Gemini 3.x returns a list of blocks (text plus
    thought signatures, or thinking blocks); only the "text" blocks are the answer."""
    content = getattr(reply, "content", None) if reply is not None else None
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            b if isinstance(b, str) else b.get("text") or ""
            for b in content
            if isinstance(b, str) or (isinstance(b, dict) and b.get("type") == "text")
        ]
        return "".join(parts).strip()
    return ""


def get_chat_model(settings: Settings) -> ChatGoogleGenerativeAI:
    if not settings.gemini_api_key:
        raise RuntimeError(
            "No Gemini API key. Put GEMINI_API_KEY=... (or GOOGLE_API_KEY=...) in the .env file."
        )
    extra: dict = {}
    if settings.llm_thinking_level:  # None = the model's own default (flash-lite: minimal)
        extra["thinking_config"] = {"thinking_level": settings.llm_thinking_level.upper()}
    return ChatGoogleGenerativeAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        api_key=settings.gemini_api_key,
        **extra,
    )
