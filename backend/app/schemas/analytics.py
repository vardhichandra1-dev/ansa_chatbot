from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AnalyticsSummary(BaseModel):
    total_interviews: int
    total_mock_sessions: int
    total_questions_practiced: int
    avg_technical_score: float | None
    avg_communication_score: float | None
    avg_confidence_score: float | None
    preparation_streak_days: int
    strong_topics: list[str]
    weak_topics: list[str]
    last_activity_at: datetime | None

    model_config = {"from_attributes": True}


class TopicPerformanceResponse(BaseModel):
    topic: str
    category: str
    questions_attempted: int
    avg_score: float | None
    last_practiced_at: datetime | None

    model_config = {"from_attributes": True}


class CompanyPrepRequest(BaseModel):
    company: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=255)


class CompanyPrepResponse(BaseModel):
    id: uuid.UUID
    company: str
    role: str
    faq: list[str]
    skill_gap_analysis: dict
    study_plan: list[dict]
    generated_at: datetime

    model_config = {"from_attributes": True}


class WeeklyReport(BaseModel):
    week_start: datetime
    week_end: datetime
    interviews_completed: int
    mock_sessions_completed: int
    questions_practiced: int
    avg_score: float | None
    top_topics: list[str]
    recommendations: list[str]
