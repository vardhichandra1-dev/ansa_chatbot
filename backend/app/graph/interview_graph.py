"""
LangGraph workflow for processing live interview transcripts.

Flow:
  START → detect_questions → analyze_followups → enrich_with_rag → END

Each node enriches the shared state and returns it.
"""
from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.agents.followup_agent import analyze_followup, rewrite_question_with_context
from app.agents.question_detection_agent import detect_questions
from app.agents.rag_agent import RAGAgent
from app.schemas.interview import TranscriptSegment
from app.services.vector_store_service import get_vector_store


class InterviewState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    segments: list[dict]          # TranscriptSegment dicts
    conversation_history: list[dict]
    detected_questions: list[dict]
    processed_questions: list[dict]  # with followup analysis + guidance
    user_id: str
    session_id: str
    error: str | None


async def detect_questions_node(state: InterviewState) -> dict[str, Any]:
    segments = [TranscriptSegment(**s) for s in state["segments"]]
    prev_questions = [q["text"] for q in state.get("detected_questions", [])]

    questions = await detect_questions(
        segments=segments,
        previous_questions=prev_questions,
    )
    return {"detected_questions": state.get("detected_questions", []) + questions}


async def analyze_followups_node(state: InterviewState) -> dict[str, Any]:
    questions = state.get("detected_questions", [])
    history = state.get("conversation_history", [])
    processed: list[dict] = []

    for q in questions:
        if q.get("is_followup"):
            result = await analyze_followup(q["text"], history)
            q["rewritten_text"] = result.get("rewritten_question", q["text"])
            q["parent_context"] = result.get("reasoning", "")
        processed.append(q)

    return {"processed_questions": processed}


async def enrich_with_rag_node(state: InterviewState) -> dict[str, Any]:
    vector_store = get_vector_store()
    rag = RAGAgent(vector_store)
    user_id = state["user_id"]
    history = state.get("conversation_history", [])
    conv_context = "\n".join(
        f"[{h['role'].upper()}]: {h['text']}" for h in history[-6:]
    )

    enriched: list[dict] = []
    for q in state.get("processed_questions", []):
        question_text = q.get("rewritten_text") or q["text"]
        guidance = await rag.generate_answer_guidance(
            question=question_text,
            user_id=user_id,
            conversation_context=conv_context,
        )
        q["guidance"] = guidance
        enriched.append(q)

    return {"processed_questions": enriched}


def _should_enrich(state: InterviewState) -> str:
    questions = state.get("processed_questions", [])
    return "enrich_with_rag" if questions else END


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
