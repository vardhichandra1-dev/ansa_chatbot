from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import get_llm
from app.schemas.interview import TranscriptSegment

SYSTEM_PROMPT = """You are an expert interview question detector.

Given a transcript segment from an interview, extract all interview questions asked by the interviewer.
For each question:
1. Identify if it is a standalone question or a follow-up to a previous question.
2. Classify the type: technical | behavioral | system_design | coding | general
3. Identify the topic (e.g., RAG, LangGraph, System Design, Leadership, etc.)

Return a JSON array. Example:
[
  {
    "text": "Can you explain how RAG works?",
    "type": "technical",
    "topic": "RAG",
    "is_followup": false,
    "timestamp_seconds": 45.2
  }
]

Return [] if no questions are detected. Return only valid JSON, no markdown."""


async def detect_questions(
    segments: list[TranscriptSegment],
    previous_questions: list[dict] | None = None,
) -> list[dict]:
    interviewer_text = [
        {"text": seg.text, "timestamp": seg.start_time}
        for seg in segments
        if seg.speaker == "interviewer"
    ]

    if not interviewer_text:
        return []

    context = ""
    if previous_questions:
        context = f"\nPrevious questions in this interview:\n{json.dumps(previous_questions[-5:], indent=2)}\n"

    llm = get_llm(temperature=0.0)
    response = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"{context}\nTranscript segments from interviewer:\n{json.dumps(interviewer_text, indent=2)}"
            ),
        ]
    )

    try:
        return json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        return []


async def classify_question(text: str) -> dict:
    """Classify a single question text."""
    llm = get_llm(temperature=0.0)
    response = await llm.ainvoke(
        [
            SystemMessage(
                content="Classify this interview question. Return JSON: "
                '{"type": "technical|behavioral|system_design|coding|general", "topic": "string"}'
            ),
            HumanMessage(content=text),
        ]
    )
    try:
        return json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        return {"type": "technical", "topic": "General"}
