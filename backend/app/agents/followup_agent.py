from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import get_fast_llm

# Compact prompt — Haiku handles this classification task well with fewer tokens
SYSTEM_PROMPT = """Determine if this interview question is a follow-up to the conversation.
Return JSON: {"is_followup": bool, "rewritten_question": "self-contained version of the question"}
If not a follow-up, rewritten_question = original question. Return ONLY JSON, no markdown."""


async def analyze_followup(
    new_question: str,
    conversation_history: list[dict],
) -> dict:
    # Only pass last 4 turns — enough context, fewer tokens
    recent = conversation_history[-4:]
    history_text = "\n".join(f"[{h['role'].upper()}]: {h['text']}" for h in recent)

    llm = get_fast_llm(temperature=0.0)
    response = await llm.ainvoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Conversation:\n{history_text}\n\nNew question: {new_question}"),
    ])

    try:
        return json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        return {"is_followup": False, "rewritten_question": new_question}
