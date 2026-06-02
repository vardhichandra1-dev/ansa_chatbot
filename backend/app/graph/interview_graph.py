"""
LangGraph workflow for batch-processing a completed interview transcript.

Used when the user uploads a full audio recording AFTER the interview.
For real-time assistance during a live interview, use LiveInterviewSession instead.

Flow:  START → detect_questions → analyze_followups → enrich_with_rag → END
"""
from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.agents.followup_agent import analyze_followup
from app.agents.question_detection_agent import detect_questions
from app.agents.rag_agent import RAGAgent
from app.schemas.interview import TranscriptSegment
from app.services.vector_store_service import get_vector_store


class InterviewState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    segments: list[dict]
    conversation_history: list[dict]
    detected_questions: list[dict]
    processed_questions: list[dict]
    session_id: str
    error: str | None


async def detect_questions_node(state: InterviewState) -> dict[str, Any]:
    segments = [TranscriptSegment(**s) for s in state["segments"]]
    prev = [q["text"] for q in state.get("detected_questions", [])]
    questions = await detect_questions(segments=segments, previous_questions=prev)
    return {"detected_questions": state.get("detected_questions", []) + questions}


async def analyze_followups_node(state: InterviewState) -> dict[str, Any]:
    history = state.get("conversation_history", [])
    processed: list[dict] = []
    for q in state.get("detected_questions", []):
        if q.get("is_followup"):
            result = await analyze_followup(q["text"], history)
            q["rewritten_text"] = result.get("rewritten_question", q["text"])
        processed.append(q)
    return {"processed_questions": processed}


async def enrich_with_rag_node(state: InterviewState) -> dict[str, Any]:
    rag = RAGAgent(get_vector_store())
    history = state.get("conversation_history", [])
    conv_ctx = "\n".join(f"[{h['role'].upper()}]: {h['text']}" for h in history[-6:])

    enriched: list[dict] = []
    for q in state.get("processed_questions", []):
        text = q.get("rewritten_text") or q["text"]
        q["guidance"] = await rag.generate_answer_guidance(text, conv_ctx)
        enriched.append(q)
    return {"processed_questions": enriched}


def _should_enrich(state: InterviewState) -> str:
    return "enrich_with_rag" if state.get("processed_questions") else END


def build_interview_graph() -> Any:
    graph = StateGraph(InterviewState)
    graph.add_node("detect_questions", detect_questions_node)
    graph.add_node("analyze_followups", analyze_followups_node)
    graph.add_node("enrich_with_rag", enrich_with_rag_node)
    graph.add_edge(START, "detect_questions")
    graph.add_edge("detect_questions", "analyze_followups")
    graph.add_conditional_edges("analyze_followups", _should_enrich)
    graph.add_edge("enrich_with_rag", END)
    return graph.compile()


interview_graph = build_interview_graph()
