"""
LiveInterviewSession — the heart of the live interview assistant.

Responsibilities:
  - Receive audio chunks from the WebSocket client
  - Transcribe each chunk with Whisper
  - Assign speaker labels (interviewer vs candidate)
  - Run question detection when the interviewer speaks
  - Analyze whether the question is a follow-up
  - Fetch RAG guidance from the resume + past questions
  - Push results back to the frontend via WebSocket in real time
  - Persist detected questions to PostgreSQL
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.followup_agent import analyze_followup
from app.agents.question_detection_agent import detect_questions
from app.agents.rag_agent import RAGAgent
from app.models.interview import Interview, InterviewQuestion
from app.services.transcription_service import apply_speaker_labels, transcribe_audio
from app.services.vector_store_service import get_vector_store


class LiveInterviewSession:
    """Holds all in-memory state for one live interview WebSocket session."""

    def __init__(self, interview_id: uuid.UUID) -> None:
        self.interview_id = interview_id
        self.conversation_history: list[dict] = []   # {role, text, timestamp}
        self.detected_questions: list[dict] = []
        self._lock = asyncio.Lock()                  # prevent overlapping LLM calls

    # ── Main entry point ────────────────────────────────────────────────────

    async def ingest_audio_chunk(
        self,
        chunk: bytes,
        websocket: WebSocket,
        db: AsyncSession,
    ) -> None:
        """
        Full pipeline for one audio chunk:
          audio bytes → Whisper → speaker labels → push transcript
          → if interviewer spoke → detect questions → follow-up check
          → RAG guidance → push to frontend → save to DB
        """
        async with self._lock:
            # 1. Transcribe
            try:
                result = await transcribe_audio(chunk)
            except Exception as exc:
                await websocket.send_json({"type": "error", "message": f"Transcription failed: {exc}"})
                return

            if not result.segments:
                return

            labeled = apply_speaker_labels(result.segments)

            # 2. Push transcript segments to frontend immediately
            for seg in labeled:
                await websocket.send_json({
                    "type": "transcript",
                    "speaker": seg.speaker,
                    "text": seg.text,
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                })
                self.conversation_history.append({
                    "role": seg.speaker,
                    "text": seg.text,
                    "timestamp": seg.start_time,
                })

            # 3. Only run question detection when interviewer spoke
            interviewer_segments = [s for s in labeled if s.speaker == "interviewer"]
            if not interviewer_segments:
                return

            await self._process_interviewer_speech(interviewer_segments, websocket, db)

    async def ingest_manual_question(
        self,
        question_text: str,
        websocket: WebSocket,
        db: AsyncSession,
    ) -> None:
        """Handle a question typed manually by the user (fallback when audio isn't available)."""
        async with self._lock:
            q_data: dict = {
                "text": question_text,
                "type": "technical",
                "topic": None,
                "is_followup": False,
                "timestamp_seconds": None,
                "rewritten_text": None,
                "source": "manual",
            }

            if self.detected_questions:
                fu = await analyze_followup(question_text, self.conversation_history)
                if fu.get("is_followup"):
                    q_data["is_followup"] = True
                    q_data["rewritten_text"] = fu.get("rewritten_question", question_text)

            guidance = await self._get_guidance(q_data)
            q_data["guidance"] = guidance
            self.detected_questions.append(q_data)

            await websocket.send_json({
                "type": "question_detected",
                "question": q_data,
                "guidance": guidance,
            })
            await self._save_question(q_data, db)

    # ── Internal helpers ────────────────────────────────────────────────────

    async def _process_interviewer_speech(
        self,
        interviewer_segments,
        websocket: WebSocket,
        db: AsyncSession,
    ) -> None:
        prev_texts = [q["text"] for q in self.detected_questions[-5:]]
        questions = await detect_questions(
            segments=interviewer_segments,
            previous_questions=prev_texts,
        )

        for q_data in questions:
            # Follow-up analysis
            if q_data.get("is_followup") and self.conversation_history:
                fu = await analyze_followup(q_data["text"], self.conversation_history)
                q_data["rewritten_text"] = fu.get("rewritten_question", q_data["text"])
                q_data["followup_reasoning"] = fu.get("reasoning", "")

            # RAG guidance
            guidance = await self._get_guidance(q_data)
            q_data["guidance"] = guidance
            self.detected_questions.append(q_data)

            # Push question + guidance to frontend
            await websocket.send_json({
                "type": "question_detected",
                "question": q_data,
                "guidance": guidance,
            })

            # Save to DB
            await self._save_question(q_data, db)

    async def _get_guidance(self, q_data: dict) -> str:
        question_text = q_data.get("rewritten_text") or q_data["text"]
        conv_context = "\n".join(
            f"[{h['role'].upper()}]: {h['text']}"
            for h in self.conversation_history[-6:]
        )
        rag = RAGAgent(get_vector_store())
        return await rag.generate_answer_guidance(
            question=question_text,
            conversation_context=conv_context,
        )

    async def _save_question(self, q_data: dict, db: AsyncSession) -> None:
        q = InterviewQuestion(
            interview_id=self.interview_id,
            text=q_data["text"],
            rewritten_text=q_data.get("rewritten_text"),
            question_type=q_data.get("type", "technical"),
            topic=q_data.get("topic"),
            timestamp_seconds=q_data.get("timestamp_seconds"),
            is_followup=q_data.get("is_followup", False),
            guidance=q_data.get("guidance"),
        )
        db.add(q)
        try:
            await db.flush()
        except Exception:
            await db.rollback()

    async def close(self, db: AsyncSession) -> None:
        """Finalize the interview — mark completed and persist full transcript."""
        result = await db.get(Interview, self.interview_id)
        if result:
            result.status = "completed"
            result.completed_at = datetime.now(UTC)
            result.raw_transcript = "\n".join(
                f"[{h['role'].upper()}] {h['text']}"
                for h in self.conversation_history
            )
            await db.flush()


# ── Global session registry (single user = one active session at a time) ───

_active: LiveInterviewSession | None = None


def get_active_session() -> LiveInterviewSession | None:
    return _active


def set_active_session(session: LiveInterviewSession | None) -> None:
    global _active
    _active = session
