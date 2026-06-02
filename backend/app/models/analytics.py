from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserAnalytics(Base):
    __tablename__ = "user_analytics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    total_interviews: Mapped[int] = mapped_column(Integer, default=0)
    total_mock_sessions: Mapped[int] = mapped_column(Integer, default=0)
    total_questions_practiced: Mapped[int] = mapped_column(Integer, default=0)
    strong_topics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    weak_topics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    avg_technical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_communication_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    preparation_streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship("User")  # noqa: F821


class TopicPerformance(Base):
    __tablename__ = "topic_performance"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)  # ai | backend | dsa | behavioral
    questions_attempted: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User")  # noqa: F821


class CompanyPrep(Base):
    __tablename__ = "company_prep"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    faq: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of questions
    skill_gap_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    study_plan: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship("User")  # noqa: F821
