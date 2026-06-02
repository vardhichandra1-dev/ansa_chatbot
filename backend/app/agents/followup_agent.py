from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import get_llm

SYSTEM_PROMPT = """You are an expert at understanding interview conversation context.

Given a new question and conversation history, determine:
1. Is this a follow-up question to a previous question?
2. If yes, which question is it following up on (by index)?
3. Rewrite the question to be self-contained with full context.

Return JSON:
{
  "is_followup": boolean,
  "parent_index": number | null,
  "rewritten_question": "The fully self-contained version of the question",
  "reasoning": "Brief explanation"
}

Return only valid JSON, no markdown."""


async def analyze_followup(
    new_question: str,
    conversation_history: list[dict],
) -> dict:
    """
    Determine if a question is a follow-up and rewrite it with context.

    conversation_history items: {"role": "interviewer|candidate", "text": "...", "timestamp": ...}
    """
    history_text = "\n".join(
        f"[{item['role'].upper()}]: {item['text']}"
        for item in conversation_history[-10:]
    )

    llm = get_llm(temperature=0.0)
    response = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"Conversation so far:\n{history_text}\n\nNew question: {new_question}"
            ),
        ]
    )

    try:
        result = json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        result = {
            "is_followup": False,
            "parent_index": None,
            "rewritten_question": new_question,
            "reasoning": "Could not parse LLM response",
        }

    return result


async def rewrite_question_with_context(
    question: str,
    resume_context: str,
    conversation_context: str,
) -> str:
    """Rewrite a vague follow-up using resume and conversation context."""
    llm = get_llm(temperature=0.1)
    response = await llm.ainvoke(
        [
            SystemMessage(
                content="Rewrite the question to be fully self-contained. "
                "Use the resume and conversation context to fill in implied references. "
                "Return only the rewritten question, no explanation."
            ),
            HumanMessage(
                content=(
                    f"Resume context:\n{resume_context}\n\n"
                    f"Recent conversation:\n{conversation_context}\n\n"
                    f"Question to rewrite: {question}"
                )
            ),
        ]
    )
    return response.content.strip()
