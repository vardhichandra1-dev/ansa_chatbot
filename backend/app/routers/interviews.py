from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.interview import Interview, InterviewQuestion
from app.schemas.interview import InterviewCreate, InterviewResponse, QuestionResponse

router = APIRouter(prefix="/interviews", tags=["interviews"])


@router.post("", response_model=InterviewResponse, status_code=201)
async def create_interview(data: InterviewCreate, db: AsyncSession = Depends(get_db)):
    interview = Interview(
        title=data.title,
        company=data.company,
        role=data.role,
        interview_type=data.interview_type,
    )
    db.add(interview)
    await db.flush()
    return interview


@router.get("", response_model=list[InterviewResponse])
async def list_interviews(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Interview)
        .order_by(Interview.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(interview_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    interview = await _get_or_404(interview_id, db)
    return interview


@router.patch("/{interview_id}/complete", response_model=InterviewResponse)
async def complete_interview(interview_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    interview = await _get_or_404(interview_id, db)
    interview.status = "completed"
    interview.completed_at = datetime.now(UTC)
    return interview


@router.delete("/{interview_id}", status_code=204)
async def delete_interview(interview_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    interview = await _get_or_404(interview_id, db)
    await db.delete(interview)


@router.get("/{interview_id}/questions", response_model=list[QuestionResponse])
async def get_questions(interview_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_or_404(interview_id, db)
    result = await db.execute(
        select(InterviewQuestion)
        .where(InterviewQuestion.interview_id == interview_id)
        .order_by(InterviewQuestion.detected_at)
    )
    return result.scalars().all()


async def _get_or_404(interview_id: uuid.UUID, db: AsyncSession) -> Interview:
    result = await db.execute(select(Interview).where(Interview.id == interview_id))
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return interview
