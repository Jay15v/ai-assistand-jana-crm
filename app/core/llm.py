"""The one place that creates the Gemini chat model (LangChain), reused by every LLM node."""

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import Settings


def get_chat_model(settings: Settings) -> ChatGoogleGenerativeAI:
    if not settings.gemini_api_key:
        raise RuntimeError(
            "No Gemini API key. Put GEMINI_API_KEY=... (or GOOGLE_API_KEY=...) in the .env file."
        )
    return ChatGoogleGenerativeAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        api_key=settings.gemini_api_key,
    )
