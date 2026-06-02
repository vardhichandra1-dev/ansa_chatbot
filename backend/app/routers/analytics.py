from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analytics_agent import (
    generate_preparation_plan,
    generate_weekly_report,
    identify_weak_areas,
)
from app.agents.rag_agent import RAGAgent
from app.database import get_db
from app.models.analytics import CompanyPrep, TopicPerformance, UserAnalytics
from app.models.interview import Interview, InterviewQuestion, MockSession
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsSummary,
    CompanyPrepRequest,
    CompanyPrepResponse,
    TopicPerformanceResponse,
    WeeklyReport,
)
from app.services.auth_service import get_current_user
from app.services.vector_store_service import get_vector_store

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def get_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(UserAnalytics).where(UserAnalytics.user_id == user.id)
    )
    analytics = result.scalar_one_or_none()
    if not analytics:
        analytics = await _build_analytics(user, db)

    return AnalyticsSummary(
        total_interviews=analytics.total_interviews,
        total_mock_sessions=analytics.total_mock_sessions,
        total_questions_practiced=analytics.total_questions_practiced,
        avg_technical_score=analytics.avg_technical_score,
        avg_communication_score=analytics.avg_communication_score,
        avg_confidence_score=analytics.avg_confidence_score,
        preparation_streak_days=analytics.preparation_streak_days,
        strong_topics=json.loads(analytics.strong_topics or "[]"),
        weak_topics=json.loads(analytics.weak_topics or "[]"),
        last_activity_at=analytics.last_activity_at,
    )


@router.get("/topics", response_model=list[TopicPerformanceResponse])
async def get_topic_performance(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(TopicPerformance)
        .where(TopicPerformance.user_id == user.id)
        .order_by(TopicPerformance.avg_score.asc().nullslast())
    )
    return result.scalars().all()


@router.get("/weekly-report", response_model=WeeklyReport)
async def get_weekly_report(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    week_start = datetime.now(UTC) - timedelta(days=7)

    interviews_result = await db.execute(
        select(func.count(Interview.id)).where(
            Interview.user_id == user.id,
            Interview.created_at >= week_start,
        )
    )
    mock_result = await db.execute(
        select(func.count(MockSession.id)).where(
            MockSession.user_id == user.id,
            MockSession.created_at >= week_start,
        )
    )

    interviews_count = interviews_result.scalar() or 0
    mock_count = mock_result.scalar() or 0

    topics_result = await db.execute(
        select(TopicPerformance).where(TopicPerformance.user_id == user.id)
    )
    topics = topics_result.scalars().all()
    topic_data = [
        {
            "topic": t.topic,
            "avg_score": t.avg_score,
            "questions_attempted": t.questions_attempted,
        }
        for t in topics
    ]

    insights = await generate_weekly_report(
        user_data={
            "interviews": interviews_count,
            "mock_sessions": mock_count,
            "questions_practiced": sum(t.questions_attempted for t in topics),
        },
        topic_performance=topic_data,
    )

    top_topics = [
        t.topic for t in sorted(topics, key=lambda x: x.avg_score or 0, reverse=True)[:3]
    ]

    return WeeklyReport(
        week_start=week_start,
        week_end=datetime.now(UTC),
        interviews_completed=interviews_count,
        mock_sessions_completed=mock_count,
        questions_practiced=sum(t.questions_attempted for t in topics),
        avg_score=None,
        top_topics=top_topics,
        recommendations=insights.get("recommendations", []),
    )


@router.post("/company-prep", response_model=CompanyPrepResponse, status_code=201)
async def generate_company_prep(
    data: CompanyPrepRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Check resume for skill extraction
    from app.models.resume import Resume

    resume_result = await db.execute(
        select(Resume).where(Resume.user_id == user.id, Resume.is_primary == True)  # noqa: E712
    )
    resume = resume_result.scalar_one_or_none()
    candidate_skills = json.loads(resume.skills or "[]") if resume else []

    vector_store = get_vector_store()
    rag = RAGAgent(vector_store)

    faq = await rag.generate_company_faq(data.company, data.role)
    skill_gap = await rag.analyze_skill_gap(candidate_skills, data.company, data.role)
    study_plan = await rag.generate_study_plan(
        data.company, data.role, skill_gap.get("gap_skills", []), weeks=4
    )

    prep = CompanyPrep(
        user_id=user.id,
        company=data.company,
        role=data.role,
        faq=json.dumps(faq),
        skill_gap_analysis=json.dumps(skill_gap),
        study_plan=json.dumps(study_plan),
    )
    db.add(prep)
    await db.flush()

    return CompanyPrepResponse(
        id=prep.id,
        company=prep.company,
        role=prep.role,
        faq=faq,
        skill_gap_analysis=skill_gap,
        study_plan=study_plan,
        generated_at=prep.generated_at,
    )


@router.get("/preparation-plan")
async def get_preparation_plan(
    days: int = 14,
    company: str | None = None,
    role: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    topics_result = await db.execute(
        select(TopicPerformance).where(TopicPerformance.user_id == user.id)
    )
    topics = topics_result.scalars().all()
    topic_data = [{"topic": t.topic, "avg_score": t.avg_score} for t in topics]

    weak_areas = await identify_weak_areas(topic_data)
    plan = await generate_preparation_plan(weak_areas, company, role, days)
    return {"days": days, "weak_areas": weak_areas, "plan": plan}


# ── Internal helpers ─────────────────────────────────────────────────────────


async def _build_analytics(user: User, db: AsyncSession) -> UserAnalytics:
    interviews_result = await db.execute(
        select(func.count(Interview.id)).where(Interview.user_id == user.id)
    )
    mock_result = await db.execute(
        select(func.count(MockSession.id)).where(MockSession.user_id == user.id)
    )

    analytics = UserAnalytics(
        user_id=user.id,
        total_interviews=interviews_result.scalar() or 0,
        total_mock_sessions=mock_result.scalar() or 0,
        total_questions_practiced=0,
        strong_topics=json.dumps([]),
        weak_topics=json.dumps([]),
    )
    db.add(analytics)
    await db.flush()
    return analytics
