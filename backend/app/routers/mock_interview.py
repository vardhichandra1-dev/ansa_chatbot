from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.graph.mock_interview_graph import (
    MockInterviewState,
    evaluate_answer_node,
    finalize_session_node,
    generate_question_node,
)
from app.models.interview import MockSession
from app.schemas.interview import (
    EvaluationResult,
    MockMessageRequest,
    MockMessageResponse,
    MockSessionCreate,
    MockSessionResponse,
)

router = APIRouter(prefix="/mock", tags=["mock-interview"])


@router.post("/sessions", response_model=MockSessionResponse, status_code=201)
async def create_session(data: MockSessionCreate, db: AsyncSession = Depends(get_db)):
    session = MockSession(
        interview_type=data.interview_type,
        company=data.company,
        role=data.role,
        topics=json.dumps(data.topics),
        conversation=json.dumps([]),
    )
    db.add(session)
    await db.flush()

    state: MockInterviewState = {
        "messages": [],
        "session_id": str(session.id),
        "user_id": "local",
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

    first_q = state.get("current_question", {})
    return _build_response(session, first_q.get("question", "Ready to begin!"))


@router.post("/sessions/{session_id}/answer", response_model=MockMessageResponse)
async def submit_answer(
    session_id: uuid.UUID,
    data: MockMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    session = await _get_or_404(session_id, db)
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")

    conversation = json.loads(session.conversation or "[]")
    current_question = _last_assistant_message(conversation)

    state: MockInterviewState = {
        "messages": [],
        "session_id": str(session.id),
        "user_id": "local",
        "interview_type": session.interview_type,
        "company": session.company,
        "role": session.role,
        "topics": json.loads(session.topics or "[]"),
        "conversation": conversation + [{"role": "user", "content": data.message}],
        "current_question": current_question,
        "last_evaluation": None,
        "scores": [],
        "question_count": _count_user_messages(conversation),
        "max_questions": 10,
        "status": "active",
        "session_feedback": None,
        "pending_user_answer": data.message,
    }

    eval_update = await evaluate_answer_node(state)
    state.update(eval_update)

    if state["question_count"] < 10:
        q_update = await generate_question_node(state)
        state.update(q_update)
        eval_data = state.get("last_evaluation")
        evaluation = EvaluationResult(**eval_data) if eval_data else None
        response = MockMessageResponse(
            role="assistant",
            content=state["current_question"]["question"],
            question_type=state["current_question"].get("type"),
            evaluation=evaluation,
        )
    else:
        final_update = await finalize_session_node(state)
        state.update(final_update)
        _apply_scores(session, state)
        response = MockMessageResponse(
            role="assistant",
            content=state["conversation"][-1]["content"],
        )

    session.conversation = json.dumps(state["conversation"])
    await db.flush()
    return response


@router.post("/sessions/{session_id}/end", response_model=MockSessionResponse)
async def end_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    session = await _get_or_404(session_id, db)
    if session.status != "completed":
        session.status = "completed"
        session.completed_at = datetime.now(UTC)
    return session


@router.get("/sessions", response_model=list[MockSessionResponse])
async def list_sessions(skip: int = 0, limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MockSession).order_by(MockSession.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.get("/sessions/{session_id}", response_model=MockSessionResponse)
async def get_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _get_or_404(session_id, db)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_or_404(session_id: uuid.UUID, db: AsyncSession) -> MockSession:
    result = await db.execute(select(MockSession).where(MockSession.id == session_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return s


def _last_assistant_message(conversation: list[dict]) -> dict | None:
    for msg in reversed(conversation):
        if msg["role"] == "assistant":
            return {"question": msg["content"], "type": "technical"}
    return None


def _count_user_messages(conversation: list[dict]) -> int:
    return sum(1 for m in conversation if m["role"] == "user")


def _apply_scores(session: MockSession, state: MockInterviewState) -> None:
    scores = state.get("scores", [])
    if not scores:
        return
    session.technical_score = sum(s.get("technical_score", 0) for s in scores) / len(scores)
    session.communication_score = sum(s.get("communication_score", 0) for s in scores) / len(scores)
    session.confidence_score = sum(s.get("confidence_score", 0) for s in scores) / len(scores)
    session.overall_score = (
        session.technical_score + session.communication_score + session.confidence_score
    ) / 3
    session.feedback_summary = state.get("session_feedback")
    session.status = "completed"
    session.completed_at = datetime.now(UTC)


def _build_response(session: MockSession, first_message: str) -> MockSessionResponse:
    return MockSessionResponse(
        id=session.id,
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
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
