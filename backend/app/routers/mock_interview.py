"""
Mock interview router.

Session lifecycle:
  POST /mock/sessions          → create session, get first question
  POST /mock/sessions/{id}/answer → submit answer, get evaluation + next question
  POST /mock/sessions/{id}/end    → end session, get final feedback
  GET  /mock/sessions          → list user sessions
  GET  /mock/sessions/{id}     → get session details
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.graph.mock_interview_graph import MockInterviewState, evaluate_answer_node, finalize_session_node, generate_question_node
from app.models.interview import MockSession
from app.models.user import User
from app.schemas.interview import (
    MockMessageRequest,
    MockMessageResponse,
    MockSessionCreate,
    MockSessionResponse,
)
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/mock", tags=["mock-interview"])


@router.post("/sessions", response_model=MockSessionResponse, status_code=201)
async def create_session(
    data: MockSessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = MockSession(
        user_id=user.id,
        interview_type=data.interview_type,
        company=data.company,
        role=data.role,
        topics=json.dumps(data.topics),
        conversation=json.dumps([]),
    )
    db.add(session)
    await db.flush()

    # Generate first question
    state: MockInterviewState = {
        "messages": [],
        "session_id": str(session.id),
        "user_id": str(user.id),
        "interview_type": data.interview_type,
        "company": data.company,
        "role": data.role,
        "topics": data.topics,
        "conversation": [],
        "current_question": None,
        "last_evaluation": None,
        "scores": [],
        "question_count": 0,
        "max_questions": 10,
        "status": "active",
        "session_feedback": None,
        "pending_user_answer": None,
    }

    updated = await generate_question_node(state)
    state.update(updated)

    session.conversation = json.dumps(state["conversation"])
    await db.flush()

    first_question = state.get("current_question", {})
    return _to_response(session, first_question.get("question", "Ready to begin!"))


@router.post("/sessions/{session_id}/answer", response_model=MockMessageResponse)
async def submit_answer(
    session_id: uuid.UUID,
    data: MockMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await _get_session(session_id, user.id, db)
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")

    conversation = json.loads(session.conversation or "[]")
    current_question = _extract_last_question(conversation)

    state: MockInterviewState = {
        "messages": [],
        "session_id": str(session.id),
        "user_id": str(user.id),
        "interview_type": session.interview_type,
        "company": session.company,
        "role": session.role,
        "topics": json.loads(session.topics or "[]"),
        "conversation": conversation + [{"role": "user", "content": data.message}],
        "current_question": current_question,
        "last_evaluation": None,
        "scores": [],
        "question_count": _count_answered(conversation),
        "max_questions": 10,
        "status": "active",
        "session_feedback": None,
        "pending_user_answer": data.message,
    }

    eval_update = await evaluate_answer_node(state)
    state.update(eval_update)

    check_result = "generate_question" if state["question_count"] < 10 else "finalize_session"

    if check_result == "generate_question":
        q_update = await generate_question_node(state)
        state.update(q_update)
        next_message = state["current_question"]["question"]
        eval_data = state.get("last_evaluation")
        from app.schemas.interview import EvaluationResult
        evaluation = EvaluationResult(**eval_data) if eval_data else None
        response = MockMessageResponse(
            role="assistant",
            content=next_message,
            question_type=state["current_question"].get("type"),
            evaluation=evaluation,
        )
    else:
        final_update = await finalize_session_node(state)
        state.update(final_update)
        session.status = "completed"
        session.completed_at = datetime.now(UTC)
        scores = state.get("scores", [])
        if scores:
            session.technical_score = sum(s.get("technical_score", 0) for s in scores) / len(scores)
            session.communication_score = sum(s.get("communication_score", 0) for s in scores) / len(scores)
            session.confidence_score = sum(s.get("confidence_score", 0) for s in scores) / len(scores)
            session.overall_score = (
                session.technical_score + session.communication_score + session.confidence_score
            ) / 3
        session.feedback_summary = state.get("session_feedback")
        response = MockMessageResponse(
            role="assistant",
            content=state["conversation"][-1]["content"],
            evaluation=None,
        )

    session.conversation = json.dumps(state["conversation"])
    await db.flush()
    return response


@router.post("/sessions/{session_id}/end", response_model=MockSessionResponse)
async def end_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await _get_session(session_id, user.id, db)
    if session.status != "completed":
        session.status = "completed"
        session.completed_at = datetime.now(UTC)
    return session


@router.get("/sessions", response_model=list[MockSessionResponse])
async def list_sessions(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MockSession)
        .where(MockSession.user_id == user.id)
        .order_by(MockSession.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/sessions/{session_id}", response_model=MockSessionResponse)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _get_session(session_id, user.id, db)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _get_session(
    session_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> MockSession:
    result = await db.execute(
        select(MockSession).where(
            MockSession.id == session_id, MockSession.user_id == user_id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _extract_last_question(conversation: list[dict]) -> dict | None:
    for msg in reversed(conversation):
        if msg["role"] == "assistant":
            return {"question": msg["content"], "type": "technical"}
    return None


def _count_answered(conversation: list[dict]) -> int:
    return sum(1 for msg in conversation if msg["role"] == "user")


def _to_response(session: MockSession, first_message: str) -> MockSessionResponse:
    return MockSessionResponse(
        id=session.id,
        user_id=session.user_id,
        interview_type=session.interview_type,
        company=session.company,
        role=session.role,
        status=session.status,
        overall_score=session.overall_score,
        technical_score=session.technical_score,
        communication_score=session.communication_score,
        confidence_score=session.confidence_score,
        feedback_summary=first_message,
        created_at=session.created_at,
        completed_at=session.completed_at,
    )
