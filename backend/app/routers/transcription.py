"""
Transcription router — two modes:
  1. POST /transcription/upload  — upload an audio file, get back a transcript
  2. POST /transcription/process — send pre-segmented transcript through the LangGraph pipeline
     to extract questions, detect follow-ups, and generate guidance.

WebSocket endpoint for real-time streaming transcription is also provided.
"""
from __future__ import annotations

import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.graph.interview_graph import interview_graph
from app.models.interview import Interview, InterviewQuestion
from app.models.user import User
from app.schemas.interview import QuestionResponse, TranscriptUploadRequest
from app.services.auth_service import get_current_user
from app.services.transcription_service import (
    apply_speaker_labels,
    transcribe_audio,
)
from app.services.vector_store_service import get_vector_store

router = APIRouter(prefix="/transcription", tags=["transcription"])


@router.post("/upload")
async def upload_audio(
    interview_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Interview).where(Interview.id == interview_id, Interview.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    audio_bytes = await file.read()
    transcript = await transcribe_audio(audio_bytes, file.filename or "audio.webm")
    labeled = apply_speaker_labels(transcript.segments)

    return {
        "full_text": transcript.full_text,
        "duration_seconds": transcript.duration,
        "language": transcript.language,
        "segments": [s.model_dump() for s in labeled],
    }


@router.post("/process", response_model=list[QuestionResponse])
async def process_transcript(
    data: TranscriptUploadRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Interview).where(Interview.id == data.interview_id, Interview.user_id == user.id)
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    state = {
        "messages": [],
        "segments": [s.model_dump() for s in data.segments],
        "conversation_history": [],
        "detected_questions": [],
        "processed_questions": [],
        "user_id": str(user.id),
        "session_id": str(interview.id),
        "error": None,
    }

    final_state = await interview_graph.ainvoke(state)
    processed = final_state.get("processed_questions", [])

    saved_questions: list[InterviewQuestion] = []
    vector_store = get_vector_store()

    for q_data in processed:
        q = InterviewQuestion(
            interview_id=interview.id,
            text=q_data["text"],
            rewritten_text=q_data.get("rewritten_text"),
            question_type=q_data.get("type", "technical"),
            topic=q_data.get("topic"),
            timestamp_seconds=q_data.get("timestamp_seconds"),
            is_followup=q_data.get("is_followup", False),
        )
        db.add(q)
        await db.flush()

        await vector_store.add_question(
            question_id=str(q.id),
            user_id=str(user.id),
            text=q.text,
            metadata={"type": q.question_type, "topic": q.topic or ""},
        )
        saved_questions.append(q)

    return saved_questions


@router.websocket("/stream/{interview_id}")
async def stream_transcription(
    websocket: WebSocket,
    interview_id: uuid.UUID,
):
    """
    WebSocket endpoint for real-time transcription streaming.
    Client sends audio chunks; server returns transcript segments.

    Protocol:
      Client → binary audio chunk (webm/opus)
      Server → JSON: {"type": "segment", "text": "...", "speaker": "...", "timestamp": ...}
      Server → JSON: {"type": "question", "question": {...}}
      Server → JSON: {"type": "error", "message": "..."}
    """
    await websocket.accept()
    buffer = bytearray()

    try:
        while True:
            data = await websocket.receive_bytes()
            buffer.extend(data)

            # Process every ~2 seconds of audio (approx 32KB at 128kbps)
            if len(buffer) >= 32_768:
                chunk = bytes(buffer)
                buffer.clear()
                try:
                    result = await transcribe_audio(chunk, "chunk.webm")
                    for seg in result.segments:
                        await websocket.send_json({
                            "type": "segment",
                            "text": seg.text,
                            "speaker": seg.speaker,
                            "start_time": seg.start_time,
                            "end_time": seg.end_time,
                        })
                except Exception as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
    except WebSocketDisconnect:
        pass
