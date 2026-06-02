"""
LangGraph workflow for mock interview sessions.

Flow:
  START → generate_question → [user answers] → evaluate_answer → check_continue
                ↑                                                        |
                └────────────────── next_question ───────────────────────┘
                                                                         |
                                                              END (session complete)
"""
from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.agents.evaluation_agent import (
    evaluate_answer,
    generate_mock_question,
    generate_session_feedback,
)
from app.schemas.interview import EvaluationResult


class MockInterviewState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    user_id: str
    interview_type: str
    company: str | None
    role: str | None
    topics: list[str]
    conversation: list[dict]       # {"role": "assistant|user", "content": "..."}
    current_question: dict | None  # generated question object
    last_evaluation: dict | None
    scores: list[dict]             # all per-question evaluations
    question_count: int
    max_questions: int
    status: Literal["active", "completed"]
    session_feedback: str | None
    pending_user_answer: str | None


async def generate_question_node(state: MockInterviewState) -> dict[str, Any]:
    question_data = await generate_mock_question(
        interview_type=state["interview_type"],
        company=state.get("company"),
        role=state.get("role"),
        topics=state.get("topics", []),
        history_length=len(state.get("conversation", [])),
    )
    conversation = list(state.get("conversation", []))
    conversation.append({"role": "assistant", "content": question_data["question"]})

    return {
        "current_question": question_data,
        "conversation": conversation,
        "pending_user_answer": None,
    }


async def evaluate_answer_node(state: MockInterviewState) -> dict[str, Any]:
    question = state.get("current_question", {})
    answer = state.get("pending_user_answer", "")

    if not answer or not question:
        return {"last_evaluation": None}

    evaluation = await evaluate_answer(
        question=question.get("question", ""),
        answer=answer,
        question_type=question.get("type", "technical"),
    )

    scores = list(state.get("scores", []))
    scores.append(
        {
            "question": question.get("question", ""),
            "type": question.get("type"),
            "topic": question.get("topic"),
            **evaluation.model_dump(),
        }
    )

    conversation = list(state.get("conversation", []))
    feedback_msg = (
        f"**Feedback:** {evaluation.feedback}"
    )
    if evaluation.missing_concepts:
        feedback_msg += f"\n\n**Key concepts to cover:** {', '.join(evaluation.missing_concepts)}"
    if evaluation.strengths:
        feedback_msg += f"\n\n**Strengths:** {', '.join(evaluation.strengths)}"

    conversation.append({"role": "assistant", "content": feedback_msg})

    return {
        "last_evaluation": evaluation.model_dump(),
        "scores": scores,
        "conversation": conversation,
        "question_count": state.get("question_count", 0) + 1,
    }


async def finalize_session_node(state: MockInterviewState) -> dict[str, Any]:
    scores = state.get("scores", [])
    if not scores:
        return {"status": "completed", "session_feedback": "Session ended."}

    avg_scores = {
        "technical": sum(s.get("technical_score", 0) for s in scores) / len(scores),
        "communication": sum(s.get("communication_score", 0) for s in scores) / len(scores),
        "completeness": sum(s.get("completeness_score", 0) for s in scores) / len(scores),
        "confidence": sum(s.get("confidence_score", 0) for s in scores) / len(scores),
    }

    feedback = await generate_session_feedback(
        conversation=state.get("conversation", []),
        scores=avg_scores,
    )

    conversation = list(state.get("conversation", []))
    conversation.append({"role": "assistant", "content": f"**Session Complete!**\n\n{feedback}"})

    return {
        "status": "completed",
        "session_feedback": feedback,
        "conversation": conversation,
    }


def _check_continue(state: MockInterviewState) -> str:
    question_count = state.get("question_count", 0)
    max_questions = state.get("max_questions", 10)
    if question_count >= max_questions:
        return "finalize_session"
    return "generate_question"


def build_mock_interview_graph() -> Any:
    graph = StateGraph(MockInterviewState)

    graph.add_node("generate_question", generate_question_node)
    graph.add_node("evaluate_answer", evaluate_answer_node)
    graph.add_node("finalize_session", finalize_session_node)

    graph.add_edge(START, "generate_question")
    graph.add_edge("generate_question", END)  # Wait for user answer
    graph.add_conditional_edges("evaluate_answer", _check_continue)
    graph.add_edge("finalize_session", END)

    return graph.compile()


mock_interview_graph = build_mock_interview_graph()
