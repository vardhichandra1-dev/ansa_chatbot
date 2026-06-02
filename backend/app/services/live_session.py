"""
LiveInterviewSession — optimized for minimum latency.

Timeline per audio chunk (after optimization):
  T+0.0s  Audio chunk arrives
  T+0.0s  Lock acquired, Whisper transcription starts
  T+0.8s  Transcript pushed to client immediately
  T+1.0s  Heuristic pre-filter (skip if no question detected without LLM)
  T+1.3s  Question detected (Haiku) — pushed to client immediately
  T+1.3s  LOCK RELEASED — next audio chunk can start processing now
  T+1.3s  Background task starts:
            ├── asyncio.gather: follow-up analysis (Haiku) + ChromaDB x2  [parallel, ~0.5s]
  T+1.8s  First guidance tokens start streaming to client (Sonnet streaming)
  T+3.5s  Full guidance delivered

Key design decisions:
  - Lock only covers transcription + question detection (the "fast path")
  - Guidance streaming runs as a background asyncio.Task outside the lock
  - Follow-up analysis + both ChromaDB searches run in parallel via asyncio.gather()
  - Background tasks are tracked so they can be cancelled on WebSocket close
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
from app.services.vector_store_service import VectorStoreService, get_vector_store


class LiveInterviewSession:

    def __init__(self, interview_id: uuid.UUID) -> None:
        self.interview_id = interview_id
        self.conversation_history: list[dict] = []
        self.detected_questions: list[dict] = []
        self._vs: VectorStoreService = get_vector_store()   # cache singleton
        self._lock = asyncio.Lock()
        self._guidance_tasks: set[asyncio.Task] = set()     # track background tasks

    # ── Primary entry point ─────────────────────────────────────────────────

    async def ingest_audio_chunk(
        self,
        chunk: bytes,
        websocket: WebSocket,
        db: AsyncSession,
        source: str = "auto",
    ) -> None:
        """
        FAST PATH (inside lock, ~1.3s):
          Whisper → speaker labels → push transcript → question detection → push question

        SLOW PATH (outside lock, background task, ~0.5-2s):
          follow-up rewrite + ChromaDB fetch + stream guidance

        source:
          "mic"    — candidate's microphone only; skip question detection
          "system" — system/meeting audio (mixed); use heuristic speaker labeling
          "auto"   — same as "system" (default)
        """
        questions_to_enrich: list[dict] = []
        conv_snapshot: list[dict] = []

        async with self._lock:
            # 1. Transcribe
            try:
                result = await transcribe_audio(chunk)
            except Exception as exc:
                await _safe_send(websocket, {"type": "error", "message": f"Transcription failed: {exc}"})
                return

            if not result.segments:
                return

            labeled = apply_speaker_labels(result.segments, source=source)

            # 2. Push transcript to client immediately
            for seg in labeled:
                await _safe_send(websocket, {
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

            # 3. Mic-only source = candidate speaking; no question detection needed
            if source == "mic":
                return

            # 4. Only proceed if interviewer spoke
            interviewer_segs = [s for s in labeled if s.speaker == "interviewer"]
            if not interviewer_segs:
                return

            # 5. Detect questions (Haiku, includes heuristic pre-filter)
            prev_texts = [q["text"] for q in self.detected_questions[-3:]]
            questions = await detect_questions(interviewer_segs, prev_texts)
            if not questions:
                return

            # 6. Push each question to client IMMEDIATELY (no waiting for guidance)
            for q_data in questions:
                await _safe_send(websocket, {
                    "type": "question_detected",
                    "question": q_data,
                    "guidance": None,   # guidance will stream separately
                })
                self.detected_questions.append(q_data)
                questions_to_enrich.append(q_data)

            # Snapshot conversation before releasing lock (background tasks read it)
            conv_snapshot = self.conversation_history[-4:]

        # ── LOCK RELEASED — fast path done ──────────────────────────────────
        # Guidance generation starts as background tasks (non-blocking)
        for q_data in questions_to_enrich:
            task = asyncio.create_task(
                self._enrich_and_stream(q_data, conv_snapshot, websocket, db)
            )
            self._guidance_tasks.add(task)
            task.add_done_callback(self._guidance_tasks.discard)

    async def ingest_manual_question(self, question_text: str, websocket: WebSocket, db: AsyncSession) -> None:
        """Typed question — push immediately then stream guidance in background."""
        q_data: dict = {
            "text": question_text,
            "type": "technical",
            "topic": None,
            "is_followup": False,
            "timestamp_seconds": None,
            "rewritten_text": None,
            "source": "manual",
        }
        await _safe_send(websocket, {
            "type": "question_detected",
            "question": q_data,
            "guidance": None,
        })
        self.detected_questions.append(q_data)

        conv_snapshot = self.conversation_history[-4:]
        task = asyncio.create_task(
            self._enrich_and_stream(q_data, conv_snapshot, websocket, db)
        )
        self._guidance_tasks.add(task)
        task.add_done_callback(self._guidance_tasks.discard)

    # ── Background enrichment task ──────────────────────────────────────────

    async def _enrich_and_stream(
        self,
        q_data: dict,
        conv_snapshot: list[dict],
        websocket: WebSocket,
        db: AsyncSession,
    ) -> None:
        """
        Runs outside the lock as a background asyncio.Task.
        Three things happen in parallel via asyncio.gather():
          1. Follow-up analysis (Haiku, only if flagged as follow-up)
          2. Resume semantic search (ChromaDB)
          3. Similar question search (ChromaDB)
        Then guidance streams token by token.
        """
        try:
            rag = RAGAgent(self._vs)
            question_text = q_data["text"]
            conv_ctx = "\n".join(f"[{h['role'].upper()}]: {h['text']}" for h in conv_snapshot)

            # Parallel fetch: follow-up rewrite + both vector searches
            fu_coro = (
                analyze_followup(question_text, conv_snapshot)
                if q_data.get("is_followup") and conv_snapshot
                else _noop()
            )
            fu_result, resume_chunks, similar_qs = await asyncio.gather(
                fu_coro,
                self._vs.search_resume(question_text, n_results=3),
                self._vs.search_similar_questions(question_text, n_results=2),
            )

            # Apply follow-up rewrite if needed
            if isinstance(fu_result, dict) and fu_result.get("is_followup"):
                q_data["rewritten_text"] = fu_result.get("rewritten_question", question_text)
                question_text = q_data["rewritten_text"]

            # Stream guidance tokens to client
            full_guidance = ""
            async for token in rag.stream_guidance(question_text, conv_ctx, resume_chunks, similar_qs):
                full_guidance += token
                sent = await _safe_send(websocket, {"type": "guidance_chunk", "text": token})
                if not sent:
                    break   # WebSocket closed

            q_data["guidance"] = full_guidance
            await _safe_send(websocket, {"type": "guidance_done"})

            # Save to DB
            await _save_question(q_data, self.interview_id, db)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            await _safe_send(websocket, {"type": "error", "message": f"Guidance error: {exc}"})

    # ── Close / cleanup ─────────────────────────────────────────────────────

    async def close(self, db: AsyncSession) -> None:
        # Cancel any in-flight guidance tasks
        for task in list(self._guidance_tasks):
            task.cancel()
        if self._guidance_tasks:
            await asyncio.gather(*self._guidance_tasks, return_exceptions=True)

        interview = await db.get(Interview, self.interview_id)
        if interview:
            interview.status = "completed"
            interview.completed_at = datetime.now(UTC)
            interview.raw_transcript = "\n".join(
                f"[{h['role'].upper()}] {h['text']}" for h in self.conversation_history
            )
            try:
                await db.flush()
            except Exception:
                pass


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _safe_send(websocket: WebSocket, data: dict) -> bool:
    """Send JSON; return False if the WebSocket is closed."""
    try:
        await websocket.send_json(data)
        return True
    except Exception:
        return False


async def _noop() -> dict:
    return {}


async def _save_question(q_data: dict, interview_id: uuid.UUID, db: AsyncSession) -> None:
    q = InterviewQuestion(
        interview_id=interview_id,
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


# ── Global session registry ──────────────────────────────────────────────────

_active: LiveInterviewSession | None = None


def get_active_session() -> LiveInterviewSession | None:
    return _active


def set_active_session(session: LiveInterviewSession | None) -> None:
    global _active
    _active = session
