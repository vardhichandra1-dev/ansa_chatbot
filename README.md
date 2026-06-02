# AI Interview Copilot

> The most advanced AI-powered interview preparation, coaching, transcription, and analytics platform — built for software engineers and AI professionals.

[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-orange)](https://langchain-ai.github.io/langgraph)
[![Anthropic Claude](https://img.shields.io/badge/LLM-Anthropic%20Claude-blueviolet)](https://anthropic.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## What it does

AI Interview Copilot is an intelligent platform that helps technical candidates prepare for, record, and analyze their interviews using AI agents.

| Capability | Description |
|---|---|
| **Live Transcription** | Upload or stream interview audio — Whisper transcribes with timestamps |
| **Question Detection** | LangGraph agent extracts and classifies every interview question |
| **Follow-up Analysis** | Understands conversational context; rewrites vague follow-ups with full context |
| **Resume-Aware Guidance** | RAG agent generates personalized answer guidance from your resume |
| **AI Mock Interviewer** | Full mock interview sessions with question generation and per-answer scoring |
| **Interview Analytics** | Topic performance, weak areas, weekly reports, company-specific prep |
| **Company Prep Generator** | FAQ, skill gap analysis, and study plan for any company/role |

---

## Architecture

```
Next.js Frontend (coming soon)
        ↓
FastAPI Backend  ←→  WebSocket (real-time transcription)
        ↓
LangGraph Orchestrator
   ├── interview_graph     (transcript → questions → follow-ups → guidance)
   └── mock_interview_graph (question gen → evaluation → session feedback)
        ↓
Agent Layer
   ├── Question Detection Agent
   ├── Follow-up Rewriter Agent
   ├── RAG Agent (resume + history retrieval)
   ├── Evaluation Agent (per-answer scoring)
   └── Analytics Agent (weekly reports, prep plans)
        ↓
   ChromaDB (vector store)    PostgreSQL (relational)    Redis (cache)
        ↓
   Anthropic Claude / OpenAI GPT-4o
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.115, Python 3.12, async SQLAlchemy 2.0 |
| AI Orchestration | LangGraph 0.2, LangChain 0.3 |
| LLM (primary) | Anthropic Claude (`claude-sonnet-4-6`) |
| LLM (fallback) | OpenAI GPT-4o |
| Speech | OpenAI Whisper API |
| Vector Store | ChromaDB (dev) / Pinecone (prod) |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Auth | JWT (access + refresh tokens), bcrypt |
| Container | Docker + Docker Compose |

---

## Project Structure

```
ai-interview-copilot/
├── docker-compose.yml          # PostgreSQL + Redis + API containers
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py             # FastAPI app, lifespan, middleware, routers
│       ├── config.py           # Pydantic settings (env-driven)
│       ├── database.py         # Async SQLAlchemy engine + session factory
│       ├── core/
│       │   └── security.py     # JWT, bcrypt, token helpers
│       ├── models/             # SQLAlchemy ORM models
│       │   ├── user.py
│       │   ├── resume.py
│       │   ├── interview.py    # Interview, InterviewQuestion, Answer, MockSession
│       │   └── analytics.py   # UserAnalytics, TopicPerformance, CompanyPrep
│       ├── schemas/            # Pydantic v2 request/response schemas
│       │   ├── auth.py
│       │   ├── interview.py
│       │   └── analytics.py
│       ├── agents/             # LangGraph agent nodes
│       │   ├── base.py                    # LLM provider factory
│       │   ├── question_detection_agent.py
│       │   ├── followup_agent.py
│       │   ├── rag_agent.py               # Resume + company prep
│       │   ├── evaluation_agent.py        # Mock interview scoring
│       │   └── analytics_agent.py
│       ├── graph/              # Compiled LangGraph state machines
│       │   ├── interview_graph.py         # Live interview pipeline
│       │   └── mock_interview_graph.py    # Mock session state machine
│       ├── routers/            # FastAPI route handlers
│       │   ├── auth.py
│       │   ├── resumes.py
│       │   ├── interviews.py
│       │   ├── transcription.py           # + WebSocket /stream endpoint
│       │   ├── mock_interview.py
│       │   └── analytics.py
│       └── services/           # Business logic / integrations
│           ├── auth_service.py
│           ├── resume_service.py
│           ├── transcription_service.py   # Whisper + speaker labeling
│           └── vector_store_service.py    # ChromaDB wrapper
```

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/vardhichandra1-dev/ai-interview-copilot.git
cd ai-interview-copilot

cp backend/.env.example backend/.env
# Edit backend/.env and set:
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPENAI_API_KEY=sk-...
#   SECRET_KEY=<long random string>
```

### 2. Run with Docker Compose

```bash
docker-compose up --build
```

Services started:
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### 3. Run locally (without Docker)

```bash
# Start postgres and redis separately, then:
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

---

## API Reference

All endpoints are under `/api/v1`. Full interactive docs at `/docs`.

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Get access + refresh tokens |
| POST | `/auth/refresh` | Rotate tokens |
| GET | `/auth/me` | Current user profile |

### Resumes
| Method | Endpoint | Description |
|---|---|---|
| POST | `/resumes` | Upload PDF/DOCX/TXT resume |
| GET | `/resumes` | List uploaded resumes |
| DELETE | `/resumes/{id}` | Delete resume |

### Live Interviews
| Method | Endpoint | Description |
|---|---|---|
| POST | `/interviews` | Create interview session |
| GET | `/interviews` | List all interviews |
| GET | `/interviews/{id}` | Get interview details |
| PATCH | `/interviews/{id}/complete` | Mark as completed |
| GET | `/interviews/{id}/questions` | List extracted questions |
| DELETE | `/interviews/{id}` | Delete interview |

### Transcription
| Method | Endpoint | Description |
|---|---|---|
| POST | `/transcription/upload` | Upload audio → transcript |
| POST | `/transcription/process` | Run LangGraph pipeline on transcript |
| WS | `/transcription/stream/{id}` | Real-time WebSocket transcription |

### Mock Interview
| Method | Endpoint | Description |
|---|---|---|
| POST | `/mock/sessions` | Start session, get first question |
| POST | `/mock/sessions/{id}/answer` | Submit answer, get evaluation + next question |
| POST | `/mock/sessions/{id}/end` | End session |
| GET | `/mock/sessions` | List mock sessions |
| GET | `/mock/sessions/{id}` | Get session with scores |

### Analytics
| Method | Endpoint | Description |
|---|---|---|
| GET | `/analytics/summary` | Overall performance summary |
| GET | `/analytics/topics` | Per-topic performance breakdown |
| GET | `/analytics/weekly-report` | AI-generated weekly insights |
| POST | `/analytics/company-prep` | Generate company-specific prep plan |
| GET | `/analytics/preparation-plan` | Personalized day-by-day study plan |

---

## LangGraph Workflows

### interview_graph — Live Interview Pipeline

```
START
  └─► detect_questions     (extract + classify questions from transcript)
        └─► analyze_followups  (determine context, rewrite with references)
              └─► enrich_with_rag  (generate personalized answer guidance)
                    └─► END
```

### mock_interview_graph — Mock Session State Machine

```
START
  └─► generate_question    (AI interviewer asks next question)
        └─► [await user answer]
              └─► evaluate_answer   (score technical/communication/completeness)
                    ├─► generate_question  (if questions remaining)
                    └─► finalize_session   (if max questions reached)
                          └─► END
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Anthropic API key (required) |
| `OPENAI_API_KEY` | — | OpenAI API key (for Whisper + fallback LLM) |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `PRIMARY_LLM_PROVIDER` | `anthropic` | `anthropic` or `openai` |
| `PRIMARY_MODEL` | `claude-sonnet-4-6` | Claude model ID |
| `TRANSCRIPTION_BACKEND` | `api` | `api` (OpenAI Whisper) or `local` |
| `VECTOR_STORE_TYPE` | `chroma` | `chroma` (dev) or `pinecone` (prod) |
| `SECRET_KEY` | — | JWT signing secret (required in prod) |

---

## Roadmap

### Phase 1 — MVP (current)
- [x] Authentication (JWT)
- [x] Resume upload and parsing
- [x] Audio transcription (Whisper)
- [x] Question detection and classification
- [x] LangGraph interview pipeline
- [x] Mock interview sessions with AI evaluation

### Phase 2
- [ ] Speaker diarization (Pyannote.audio)
- [ ] Real-time WebSocket transcription (front-end integration)
- [ ] Interview knowledge base UI
- [ ] Company-specific question bank

### Phase 3
- [ ] Next.js frontend
- [ ] Interview analytics dashboard
- [ ] Preparation streak tracking

### Phase 4
- [ ] Desktop app (Electron)
- [ ] Chrome extension for live interviews
- [ ] Mobile application
- [ ] Multi-language support

---

## Target Users

- **GenAI Engineers** — preparing for OpenAI, Anthropic, Google, Microsoft
- **Software Engineers** — DSA, System Design, Backend Engineering interviews
- **Working Professionals** — interview prep + note storage + career tracking

---

## License

MIT — see [LICENSE](LICENSE)

---

## Author

**Chandramohan Vardhi** — Generative AI Engineer  
[GitHub](https://github.com/vardhichandra1-dev) · [Email](mailto:vardhichandra1@gmail.com)
