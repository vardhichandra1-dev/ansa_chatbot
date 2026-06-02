"""
AI Interview Copilot — FastAPI Application
==========================================
Intelligent interview preparation, coaching, transcription, and analytics platform.

Architecture:
    Next.js Frontend
        ↓
    FastAPI (this file)
        ↓
    LangGraph Orchestrator
        ↓
    Agent Layer (question detection, RAG, evaluation, analytics)
        ↓
    Vector DB (ChromaDB/Pinecone) + PostgreSQL
        ↓
    LLM Providers (Anthropic Claude / OpenAI)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import settings
from app.database import create_tables
from app.routers import analytics, auth, interviews, mock_interview, resumes, transcription

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Interview Copilot API...")
    await create_tables()
    logger.info("Database tables ready.")
    yield
    logger.info("Shutting down AI Interview Copilot API.")


app = FastAPI(
    title="AI Interview Copilot",
    description=(
        "Intelligent interview preparation, coaching, transcription, and analytics platform "
        "for software engineers and AI professionals."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router, prefix="/api/v1")
app.include_router(resumes.router, prefix="/api/v1")
app.include_router(interviews.router, prefix="/api/v1")
app.include_router(transcription.router, prefix="/api/v1")
app.include_router(mock_interview.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "AI Interview Copilot", "version": "1.0.0"}


@app.get("/", tags=["root"])
async def root():
    return {
        "message": "AI Interview Copilot API",
        "docs": "/docs",
        "version": "1.0.0",
    }
