from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import get_fast_llm
from app.schemas.interview import TranscriptSegment

# Compact prompt — fewer tokens = faster response
SYSTEM_PROMPT = """Extract interview questions from interviewer speech.
For each question return JSON with: text, type (technical|behavioral|system_design|coding|general), topic, is_followup (bool), timestamp_seconds.
Return [] if no questions. Return ONLY a JSON array, no markdown."""

# Words/patterns that indicate a question is likely present.
# If none match we skip the LLM call entirely (~0.5s saved per non-question chunk).
_QUESTION_INDICATORS = (
    "?", "what", "how", "why", "tell me", "explain", "describe",
    "walk me through", "can you", "could you", "would you", "have you",
    "do you", "did you", "when", "where", "which", "who", "give me an example",
    "talk me through", "help me understand",
)


def _likely_contains_question(text: str) -> bool:
    lower = text.lower()
    return any(ind in lower for ind in _QUESTION_INDICATORS)


async def detect_questions(
    segments: list[TranscriptSegment],
    previous_questions: list[str] | None = None,
) -> list[dict]:
    interviewer_text = [
        {"text": seg.text, "timestamp": seg.start_time}
        for seg in segments
        if seg.speaker == "interviewer"
    ]
    if not interviewer_text:
        return []

    combined = " ".join(item["text"] for item in interviewer_text)

    # Heuristic pre-filter: skip LLM for filler words ("okay", "I see", "alright")
    if not _likely_contains_question(combined):
        return []

    # Pass only last 3 previous questions to keep prompt short
    context = ""
    if previous_questions:
        context = f"Previous questions: {json.dumps(previous_questions[-3:])}\n"

    llm = get_fast_llm(temperature=0.0)
    response = await llm.ainvoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"{context}Interviewer said: {json.dumps(interviewer_text)}"),
    ])

    try:
        return json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        return []
