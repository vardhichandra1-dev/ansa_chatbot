"""
Live Interview Transcription & Assistance Router
=================================================

PRIMARY ENDPOINT — WebSocket /live/{interview_id}

Optimized latency timeline per audio chunk:
  T+0.0s  Audio chunk arrives (16KB buffer ≈ 1 second of audio)
  T+0.8s  Transcript pushed to client (Whisper)
  T+1.0s  Heuristic pre-filter (no LLM cost for "okay / I see / hmm")
  T+1.3s  Question pushed to client immediately (Haiku detection)
  T+1.3s  Lock released — next audio chunk starts processing
  T+1.8s  Follow-up rewrite + ChromaDB fetches complete (parallel)
  T+1.8s  First guidance tokens start streaming (Sonnet streaming)
  T+3.5s  Full guidance delivered

WebSocket message protocol:

  Client → Server (binary):
    Raw audio bytes (webm/opus/mp3 — any format Whisper accepts)

  Client → Server (text/JSON):
    {"type": "manual_question", "question": "Tell me about RAG"}
    {"type": "flush"}   — process current buffer immediately
    {"type": "end"}     — save transcript + close session

  Server → Client (JSON):
    {"type": "transcript",        "speaker": "interviewer|candidate",
                                  "text": "...", "start_time": 0.0, "end_time": 1.2}

    {"type": "question_detected", "question": {
        "text": "...", "rewritten_text": "...",
        "type": "technical|behavioral|system_design|coding",
        "topic": "RAG", "is_followup": false,
        "timestamp_seconds": 45.2},
     "guidance": null}             ← null here; guidance arrives via next two messages

    {"type": "guidance_chunk",    "text": "**Key points"}  ← streamed token by token
    {"type": "guidance_done"}                              ← guidance complete

    {"type": "status",  "message": "..."}
    {"type": "error",   "message": "..."}
    {"type": "session_closed"}
"""
from __future__ import annotations

import asyncio
import json
import uuid

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.graph.interview_graph import interview_graph
from app.models.interview import Interview, InterviewQuestion
from app.schemas.interview import QuestionResponse, TranscriptUploadRequest
from app.services.live_session import LiveInterviewSession, get_active_session, set_active_session
from app.services.transcription_service import apply_speaker_labels, transcribe_audio
from app.services.vector_store_service import get_vector_store

router = APIRouter(prefix="/transcription", tags=["transcription"])

# Buffer size: 16KB ≈ 1 second of audio at 128kbps.
# Smaller = lower latency; too small (< 8KB) degrades Whisper accuracy.
_CHUNK_SIZE = 16_384


# ── WebSocket — Live Interview (PRIMARY FEATURE) ────────────────────────────

@router.websocket("/live/{interview_id}")
async def live_interview_stream(
    websocket: WebSocket,
    interview_id: uuid.UUID,
    source: Literal["system", "mic", "auto"] = Query(default="auto"),
    db: AsyncSession = Depends(get_db),
):
    """
    Real-time live interview assistant WebSocket.
    Connect once per interview session; stream audio throughout.
    """
    # Verify interview exists
    result = await db.execute(select(Interview).where(Interview.id == interview_id))
    interview = result.scalar_one_or_none()
    if not interview:
        await websocket.close(code=4004, reason="Interview not found")
        return

    await websocket.accept()
    session = LiveInterviewSession(interview_id)
    set_active_session(session)

    # Companion sends 3-second chunks (~48KB at 128kbps webm/opus).
    # Use a lower threshold so we don't buffer multiple chunks before processing.
    chunk_threshold = _CHUNK_SIZE if source == "auto" else max(_CHUNK_SIZE // 2, 8_192)

    buffer = bytearray()

    source_label = {"mic": "microphone", "system": "meeting audio", "auto": "auto-detect"}[source]
    await websocket.send_json({
        "type": "status",
        "message": f"Connected to '{interview.title}'. Audio source: {source_label}. Start speaking.",
    })

    try:
        while True:
            message = await asyncio.wait_for(websocket.receive(), timeout=60.0)

            # ── Binary: audio chunk ─────────────────────────────────────────
            if "bytes" in message and message["bytes"]:
                buffer.extend(message["bytes"])

                if len(buffer) >= chunk_threshold:
                    chunk = bytes(buffer)
                    buffer.clear()
                    await websocket.send_json({"type": "status", "message": "Transcribing..."})
                    await session.ingest_audio_chunk(chunk, websocket, db, source=source)

            # ── Text: control message ───────────────────────────────────────
            elif "text" in message and message["text"]:
                try:
                    ctrl = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                msg_type = ctrl.get("type")

                if msg_type == "flush" and buffer:
                    chunk = bytes(buffer)
                    buffer.clear()
                    await websocket.send_json({"type": "status", "message": "Transcribing..."})
                    await session.ingest_audio_chunk(chunk, websocket, db, source=source)

                elif msg_type == "manual_question":
                    question_text = ctrl.get("question", "").strip()
                    if question_text:
                        await session.ingest_manual_question(question_text, websocket, db)

                elif msg_type == "end":
                    break

    except asyncio.TimeoutError:
        # 60s silence — keep connection alive with a ping
        await websocket.send_json({"type": "status", "message": "Waiting for audio..."})
    except WebSocketDisconnect:
        pass
    finally:
        # Flush remaining audio buffer
        if buffer:
            try:
                await session.ingest_audio_chunk(bytes(buffer), websocket, db, source=source)
            except Exception:
                pass

        await session.close(db)
        set_active_session(None)

        try:
            await websocket.send_json({"type": "session_closed"})
        except Exception:
            pass


# ── REST: Upload audio file (post-interview batch processing) ───────────────

@router.post("/upload")
async def upload_audio(
    interview_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a full interview recording. Returns the full transcript."""
    result = await db.execute(select(Interview).where(Interview.id == interview_id))
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


# ── REST: Process transcript through full LangGraph pipeline ────────────────

@router.post("/process", response_model=list[QuestionResponse])
async def process_transcript(
    data: TranscriptUploadRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Run a pre-segmented transcript through the full LangGraph pipeline:
    question detection → follow-up analysis → RAG guidance.
    Saves all detected questions to the interview record.
    """
    result = await db.execute(select(Interview).where(Interview.id == data.interview_id))
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    state = {
        "messages": [],
        "segments": [s.model_dump() for s in data.segments],
        "conversation_history": [],
        "detected_questions": [],
        "processed_questions": [],
        "session_id": str(interview.id),
        "error": None,
    }

    final_state = await interview_graph.ainvoke(state)
    vector_store = get_vector_store()
    saved: list[InterviewQuestion] = []

    for q_data in final_state.get("processed_questions", []):
        q = InterviewQuestion(
            interview_id=interview.id,
            text=q_data["text"],
            rewritten_text=q_data.get("rewritten_text"),
            question_type=q_data.get("type", "technical"),
            topic=q_data.get("topic"),
            timestamp_seconds=q_data.get("timestamp_seconds"),
            is_followup=q_data.get("is_followup", False),
            guidance=q_data.get("guidance"),
        )
        db.add(q)
        await db.flush()
        await vector_store.add_question(
            question_id=str(q.id),
            text=q.text,
            metadata={"type": q.question_type, "topic": q.topic or ""},
        )
        saved.append(q)

    return saved


# ── REST: Get instant guidance for a single question (no audio needed) ───────

@router.get("/guidance")
async def get_instant_guidance(question: str):
    """
    Get answer guidance for any question text on demand.
    No interview session required — useful for ad-hoc prep.
    """
    from app.agents.rag_agent import RAGAgent
    rag = RAGAgent(get_vector_store())
    guidance = await rag.generate_answer_guidance(question)
    return {"question": question, "guidance": guidance}
