from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analytics_agent import generate_preparation_plan, generate_weekly_report, identify_weak_areas
from app.agents.rag_agent import RAGAgent
from app.database import get_db
from app.models.analytics import CompanyPrep, TopicPerformance, UserAnalytics
from app.models.interview import Interview, MockSession
from app.models.resume import Resume
from app.schemas.analytics import (
    AnalyticsSummary,
    CompanyPrepRequest,
    CompanyPrepResponse,
    TopicPerformanceResponse,
    WeeklyReport,
)
from app.services.vector_store_service import get_vector_store

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def get_summary(db: AsyncSession = Depends(get_db)):
    analytics = await _get_or_create_analytics(db)
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
async def get_topic_performance(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TopicPerformance).order_by(TopicPerformance.avg_score.asc().nullslast())
    )
    return result.scalars().all()


@router.get("/weekly-report", response_model=WeeklyReport)
async def get_weekly_report(db: AsyncSession = Depends(get_db)):
    week_start = datetime.now(UTC) - timedelta(days=7)

    interviews_count = (await db.execute(
        select(func.count(Interview.id)).where(Interview.created_at >= week_start)
    )).scalar() or 0

    mock_count = (await db.execute(
        select(func.count(MockSession.id)).where(MockSession.created_at >= week_start)
    )).scalar() or 0

    topics = (await db.execute(select(TopicPerformance))).scalars().all()
    topic_data = [{"topic": t.topic, "avg_score": t.avg_score, "questions_attempted": t.questions_attempted} for t in topics]

    insights = await generate_weekly_report(
        user_data={"interviews": interviews_count, "mock_sessions": mock_count,
                   "questions_practiced": sum(t.questions_attempted for t in topics)},
        topic_performance=topic_data,
    )

    top_topics = [t.topic for t in sorted(topics, key=lambda x: x.avg_score or 0, reverse=True)[:3]]

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
async def generate_company_prep(data: CompanyPrepRequest, db: AsyncSession = Depends(get_db)):
    resume_result = await db.execute(select(Resume).where(Resume.is_active == True))  # noqa: E712
    resume = resume_result.scalar_one_or_none()
    candidate_skills = json.loads(resume.skills or "[]") if resume else []

    rag = RAGAgent(get_vector_store())
    faq = await rag.generate_company_faq(data.company, data.role)
    skill_gap = await rag.analyze_skill_gap(candidate_skills, data.company, data.role)
    study_plan = await rag.generate_study_plan(data.company, data.role, skill_gap.get("gap_skills", []))

    prep = CompanyPrep(
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
):
    topics = (await db.execute(select(TopicPerformance))).scalars().all()
    topic_data = [{"topic": t.topic, "avg_score": t.avg_score} for t in topics]
    weak_areas = await identify_weak_areas(topic_data)
    plan = await generate_preparation_plan(weak_areas, company, role, days)
    return {"days": days, "weak_areas": weak_areas, "plan": plan}


async def _get_or_create_analytics(db: AsyncSession) -> UserAnalytics:
    result = await db.execute(select(UserAnalytics).where(UserAnalytics.id == 1))
    analytics = result.scalar_one_or_none()
    if not analytics:
        i_count = (await db.execute(select(func.count(Interview.id)))).scalar() or 0
        m_count = (await db.execute(select(func.count(MockSession.id)))).scalar() or 0
        analytics = UserAnalytics(id=1, total_interviews=i_count, total_mock_sessions=m_count)
        db.add(analytics)
        await db.flush()
    return analytics
