from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InterviewCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    company: str | None = None
    role: str | None = None
    interview_type: Literal["live", "mock"] = "live"


class InterviewResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    company: str | None
    role: str | None
    interview_type: str
    status: str
    duration_seconds: int | None
    overall_score: float | None
    notes: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class TranscriptSegment(BaseModel):
    speaker: str  # "interviewer" | "candidate" | "unknown"
    text: str
    start_time: float
    end_time: float


class TranscriptUploadRequest(BaseModel):
    interview_id: uuid.UUID
    segments: list[TranscriptSegment]


class QuestionResponse(BaseModel):
    id: uuid.UUID
    interview_id: uuid.UUID
    text: str
    rewritten_text: str | None
    question_type: str
    topic: str | None
    timestamp_seconds: float | None
    is_followup: bool
    parent_question_id: uuid.UUID | None
    detected_at: datetime

    model_config = {"from_attributes": True}


class AnswerResponse(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    guidance_text: str | None
    candidate_answer: str | None
    technical_score: float | None
    communication_score: float | None
    completeness_score: float | None
    feedback: str | None
    missing_concepts: list[str] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MockSessionCreate(BaseModel):
    interview_type: Literal["technical", "behavioral", "system_design", "coding"]
    company: str | None = None
    role: str | None = None
    topics: list[str] = Field(default_factory=list)


class MockSessionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    interview_type: str
    company: str | None
    role: str | None
    status: str
    overall_score: float | None
    technical_score: float | None
    communication_score: float | None
    confidence_score: float | None
    feedback_summary: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class MockMessageRequest(BaseModel):
    session_id: uuid.UUID
    message: str


class MockMessageResponse(BaseModel):
    role: Literal["assistant", "user"]
    content: str
    question_type: str | None = None
    evaluation: EvaluationResult | None = None


class EvaluationResult(BaseModel):
    technical_score: float = Field(ge=0, le=10)
    communication_score: float = Field(ge=0, le=10)
    completeness_score: float = Field(ge=0, le=10)
    confidence_score: float = Field(ge=0, le=10)
    feedback: str
    missing_concepts: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)


MockMessageResponse.model_rebuild()
