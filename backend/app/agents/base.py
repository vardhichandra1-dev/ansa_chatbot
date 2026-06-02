from __future__ import annotations

from app.config import settings


def get_llm(temperature: float = 0.2, streaming: bool = False):
    """Primary model (Sonnet) — used for high-quality guidance generation."""
    if settings.primary_llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.primary_model,
            api_key=settings.anthropic_api_key,
            temperature=temperature,
            streaming=streaming,
        )
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=settings.fallback_model,
        api_key=settings.openai_api_key,
        temperature=temperature,
        streaming=streaming,
    )


def get_fast_llm(temperature: float = 0.0):
    """
    Fast model (Haiku) — used for classification tasks that don't need
    deep reasoning: question detection, follow-up analysis, topic labeling.
    ~3x faster and ~10x cheaper than Sonnet.
    """
    if settings.primary_llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.fast_model,
            api_key=settings.anthropic_api_key,
            temperature=temperature,
        )
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.openai_api_key,
        temperature=temperature,
    )
