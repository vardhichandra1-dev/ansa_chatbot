from __future__ import annotations

from app.config import settings


def get_llm(temperature: float = 0.2, streaming: bool = False):
    """Return the configured primary LLM with LangChain interface."""
    if settings.primary_llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.primary_model,
            api_key=settings.anthropic_api_key,
            temperature=temperature,
            streaming=streaming,
        )
    else:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.fallback_model,
            api_key=settings.openai_api_key,
            temperature=temperature,
            streaming=streaming,
        )
