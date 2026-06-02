"""
AI Interview Copilot — Personal Live Interview Assistant
=========================================================
Single-user, no authentication required.
Primary feature: real-time live interview assistance via WebSocket.

Quick start:
  1. cp .env.example .env  (set ANTHROPIC_API_KEY + OPENAI_API_KEY)
  2. docker-compose up
  3. Upload your resume: POST /api/v1/resumes
  4. Create an interview: POST /api/v1/interviews
  5. Connect WebSocket:  ws://localhost:8000/api/v1/transcription/live/{interview_id}
  6. Stream audio → get real-time transcription + question detection + answer guidance
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.database import create_tables
from app.routers import analytics, interviews, mock_interview, profile, resumes, transcription

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Interview Copilot...")
    await create_tables()
    logger.info("Database ready. Visit /docs to explore the API.")
    yield
    logger.info("Shutting down AI Interview Copilot.")


app = FastAPI(
    title="AI Interview Copilot",
    description=(
        "Personal live interview assistant — real-time transcription, "
        "question detection, and AI-powered answer guidance."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware ─────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── Routers ────────────────────────────────────────────────────────────────────

API = "/api/v1"
app.include_router(profile.router,          prefix=API)
app.include_router(resumes.router,          prefix=API)
app.include_router(interviews.router,       prefix=API)
app.include_router(transcription.router,    prefix=API)
app.include_router(mock_interview.router,   prefix=API)
app.include_router(analytics.router,        prefix=API)


# ── Companion app — served at /companion ──────────────────────────────────────

_COMPANION_HTML = Path(__file__).parent.parent.parent / "companion" / "index.html"


@app.get("/companion", tags=["companion"], include_in_schema=False)
async def companion_app():
    """Serve the live meeting companion web app."""
    if _COMPANION_HTML.exists():
        return FileResponse(_COMPANION_HTML, media_type="text/html")
    return {"error": "Companion app not found. Run from repo root."}


# ── Health + root ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/", tags=["root"])
async def root():
    return {
        "service": "AI Interview Copilot",
        "version": "2.0.0",
        "docs": "/docs",
        "companion_app": "http://localhost:8000/companion",
        "primary_feature": "WebSocket ws://localhost:8000/api/v1/transcription/live/{interview_id}",
        "quick_start": {
            "0_open_companion":   "GET  /companion  (use during Teams/Meet/Zoom)",
            "1_upload_resume":    "POST /api/v1/resumes",
            "2_create_interview": "POST /api/v1/interviews",
            "3_connect_ws":       "WS   /api/v1/transcription/live/{id}?source=system|mic|auto",
            "4_stream_audio":     "Send binary audio chunks over WebSocket",
            "5_get_guidance":     "GET  /api/v1/transcription/guidance?question=...",
        },
    }
