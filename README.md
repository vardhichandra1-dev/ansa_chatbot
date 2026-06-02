# AI Interview Copilot

> A personal AI-powered interview assistant — live transcription, real-time answer guidance, mock interview practice, and performance analytics. Built for a single user: you.

[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-orange)](https://langchain-ai.github.io/langgraph)
[![Claude Sonnet](https://img.shields.io/badge/LLM-Claude%20Sonnet-blueviolet)](https://anthropic.com)
[![Claude Haiku](https://img.shields.io/badge/Speed-Claude%20Haiku-purple)](https://anthropic.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## Live Meeting Companion

> Use during actual interviews on **Google Meet, Microsoft Teams, Zoom, or any video platform** — no integrations needed.

![Companion App in Teams/Meet](docs/screenshots/05_companion_app.svg)

Open `http://localhost:8000/companion` in a browser window and pin it alongside your video call. The companion captures meeting audio via screen share, detects questions from the interviewer, and streams AI guidance in real time — all while you stay focused on the conversation.

**How to use it during a real interview:**
1. Start the backend: `docker-compose up` or `uvicorn app.main:app`
2. Open `http://localhost:8000/companion` in a separate browser window
3. Select **Meeting Audio (system)** as the audio source
4. Click **Start Live Session**
5. When prompted to share screen/audio, select your Teams/Meet/Zoom window and **check "Share audio"**
6. Position the companion window on a second monitor or in a corner of your screen
7. Guidance streams automatically as the interviewer speaks

**Audio source options:**

| Mode | Captures | Best for |
|---|---|---|
| Meeting Audio (system) | All meeting audio via screen share | Default — works with any platform |
| Microphone only | Your voice only | Tracking what you say; no question detection |
| Both (merged) | Mic + meeting audio combined | Highest accuracy |

---

## Screenshots

### Live Interview Assistant — Real-time guidance in under 2 seconds

![Live Interview](docs/screenshots/01_live_interview.svg)

> **Left:** Real-time transcript with interviewer / candidate speaker labels streaming as you speak.  
> **Right:** As soon as a question is detected, answer guidance starts streaming token-by-token — key points, resume-aware examples, framework, and common mistakes to avoid.

---

### Mock Interview Practice — AI interviewer with per-answer scoring

![Mock Interview](docs/screenshots/02_mock_interview.svg)

> The AI interviewer asks company-specific technical questions. Each answer is scored across four dimensions: Technical Depth, Communication, Completeness, and Confidence. Detailed feedback helps you improve on every round.

---

### Analytics Dashboard — Track progress over time

![Analytics](docs/screenshots/03_analytics.svg)

> Topic performance bar chart, weak-area highlights, 14-day score trend, and an AI-generated weekly report surfacing what to prioritize next.

---

### Profile & Setup — Configure your copilot once

![Setup](docs/screenshots/04_setup.svg)

> Set your name, target role, and companies. Upload your resume (PDF/DOCX) — it is vectorized into ChromaDB and used to personalize every guidance response. The Company Prep Generator builds a custom FAQ, skill-gap analysis, and study plan for any company/role pair.

---

## What it does

| Capability | Description |
|---|---|
| **Live Transcription** | Stream audio over WebSocket — Whisper transcribes with timestamps and speaker labels |
| **Question Detection** | Haiku-powered agent classifies every interviewer question in ~300ms |
| **Follow-up Analysis** | Understands context; rewrites vague follow-ups into self-contained questions |
| **Resume-Aware Guidance** | Sonnet streams personalized answer guidance referencing your resume |
| **AI Mock Interviewer** | Full mock sessions with AI question generation and per-answer scoring |
| **Performance Analytics** | Topic trends, weak areas, 14-day score graph, AI weekly reports |
| **Company Prep** | FAQ generation, skill-gap analysis, and day-by-day study plan for any company |

---

## Latency Profile (Live Interview Path)

The system is optimized to get the first guidance token in front of you **before your interviewer finishes their next sentence**.

```
T+0.0s  Audio chunk arrives (16 KB ≈ 1 second of audio)
T+0.8s  Whisper transcript → pushed to client immediately
T+1.0s  Heuristic pre-filter (skip LLM for "okay / I see / hmm")
T+1.3s  Haiku detects question → pushed to client immediately
T+1.3s  Lock released — next audio chunk starts processing
T+1.8s  Follow-up rewrite + ChromaDB resume/question fetches (parallel)
T+1.8s  First Sonnet guidance tokens start streaming
T+3.5s  Full guidance delivered
```

Key design decisions:
- **Lock only covers the fast path** (transcription + detection). Guidance generation runs as a background `asyncio.Task` outside the lock.
- **`asyncio.gather()`** runs follow-up analysis, resume search, and similar-question search in parallel.
- **Sonnet streaming** — tokens arrive incrementally via `llm.astream()` so the UI starts rendering at T+1.8s.

---

## Architecture

```
Next.js Frontend (planned)
        ↓
FastAPI Backend  ←→  WebSocket /transcription/live/{interview_id}
        ↓
LiveInterviewSession (in-memory per connection)
   ├── FAST PATH (locked, ~1.3s):  Whisper → speaker labels → Haiku question detection
   └── SLOW PATH (background task, ~0.5-2s):
         ├── asyncio.gather: follow-up analysis (Haiku) + resume search + similar-Q search
         └── stream_guidance: Sonnet token streaming → WebSocket
        ↓
LangGraph (batch processing & mock interview)
   ├── interview_graph       (transcript → questions → follow-ups → RAG)
   └── mock_interview_graph  (generate_question → evaluate_answer → loop/end)
        ↓
   ChromaDB (vector store)    PostgreSQL (relational)    Redis (cache)
        ↓
   Claude Haiku (speed)   /   Claude Sonnet (quality)   /   Whisper (speech)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.115, Python 3.12, async SQLAlchemy 2.0 |
| AI Orchestration | LangGraph 0.2, LangChain 0.3 |
| LLM — Guidance | Claude Sonnet (`claude-sonnet-4-6`) — streaming |
| LLM — Speed tasks | Claude Haiku (`claude-haiku-4-5-20251001`) — question detection, follow-up |
| LLM — Fallback | OpenAI GPT-4o |
| Speech-to-Text | OpenAI Whisper API |
| Vector Store | ChromaDB (local, persistent) |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Container | Docker + Docker Compose |

---

## Project Structure

```
ansa_chatbot/
├── docker-compose.yml          # PostgreSQL + Redis + API containers
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py             # FastAPI app, lifespan (creates tables), 6 routers
│       ├── config.py           # Pydantic settings — primary_model, fast_model
│       ├── database.py         # Async SQLAlchemy engine + session factory
│       ├── models/
│       │   ├── profile.py      # Single-user profile (id=1, name, target_role, company)
│       │   ├── resume.py       # Uploaded resumes + chroma_doc_id
│       │   ├── interview.py    # Interview, InterviewQuestion, Answer, MockSession
│       │   └── analytics.py    # UserAnalytics, TopicPerformance, CompanyPrep
│       ├── agents/
│       │   ├── base.py                     # get_llm() / get_fast_llm()
│       │   ├── question_detection_agent.py # Haiku + heuristic pre-filter
│       │   ├── followup_agent.py           # Haiku context analysis
│       │   ├── rag_agent.py                # Sonnet streaming guidance
│       │   ├── evaluation_agent.py         # Mock interview scoring
│       │   └── analytics_agent.py          # Reports + prep plans
│       ├── graph/
│       │   ├── interview_graph.py          # Batch transcript pipeline
│       │   └── mock_interview_graph.py     # Mock session state machine
│       ├── routers/
│       │   ├── profile.py                  # GET/PUT /profile (single user)
│       │   ├── resumes.py                  # Upload / list / delete
│       │   ├── interviews.py               # CRUD
│       │   ├── transcription.py            # WebSocket /live/{id} + REST helpers
│       │   ├── mock_interview.py           # Session lifecycle
│       │   └── analytics.py               # Summary, topics, weekly report
│       └── services/
│           ├── live_session.py             # LiveInterviewSession (core real-time logic)
│           ├── transcription_service.py    # Whisper + speaker gap labeling
│           ├── resume_service.py           # pdfplumber / docx parsing
│           └── vector_store_service.py     # ChromaDB wrapper (3 collections)
└── docs/
    └── screenshots/                        # UI mockups
```

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/vardhichandra1-dev/ansa_chatbot.git
cd ansa_chatbot

cp backend/.env.example backend/.env
# Edit backend/.env — at minimum set:
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPENAI_API_KEY=sk-...      (Whisper + GPT-4o fallback)
```

### 2. Run with Docker Compose

```bash
docker-compose up --build
```

| Service | URL |
|---|---|
| **Live Meeting Companion** | **http://localhost:8000/companion** |
| API | http://localhost:8000 |
| Interactive docs | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

### 3. Run locally (without Docker)

```bash
# Start postgres and redis separately, then:
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. First-time setup (no login required)

```bash
# 1. Set your profile (runs once)
curl -X PUT http://localhost:8000/api/v1/profile \
  -H 'Content-Type: application/json' \
  -d '{"name":"Your Name","target_role":"Senior SWE","target_company":"Google"}'

# 2. Upload your resume
curl -X POST http://localhost:8000/api/v1/resumes \
  -F "file=@/path/to/resume.pdf"

# 3. Create an interview session
curl -X POST http://localhost:8000/api/v1/interviews \
  -H 'Content-Type: application/json' \
  -d '{"title":"Google FAANG Prep","company":"Google","role":"Senior SWE"}'
# Returns: {"id": "<uuid>", ...}

# 4. Connect WebSocket (use the interview id from step 3)
# ws://localhost:8000/api/v1/transcription/live/<interview_id>
```

---

## API Reference

All endpoints are under `/api/v1`. Interactive docs at `/docs`.

### Profile (single user — no auth required)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/profile` | Get your profile |
| PUT | `/profile` | Update name, role, company |

### Resumes
| Method | Endpoint | Description |
|---|---|---|
| POST | `/resumes` | Upload PDF/DOCX/TXT resume (vectorized into ChromaDB) |
| GET | `/resumes` | List uploaded resumes |
| DELETE | `/resumes/{id}` | Delete resume |

### Live Interviews
| Method | Endpoint | Description |
|---|---|---|
| POST | `/interviews` | Create interview session |
| GET | `/interviews` | List all sessions |
| GET | `/interviews/{id}` | Get session + questions |
| PATCH | `/interviews/{id}/complete` | Mark completed |
| GET | `/interviews/{id}/questions` | List extracted questions with guidance |
| DELETE | `/interviews/{id}` | Delete session |

### Transcription
| Method | Endpoint | Description |
|---|---|---|
| **WS** | `/transcription/live/{id}` | **PRIMARY** — real-time audio → guidance streaming |
| POST | `/transcription/upload` | Upload full recording → transcript |
| POST | `/transcription/process` | Batch: run LangGraph pipeline on a transcript |
| GET | `/transcription/guidance?question=...` | On-demand guidance for any question |

### Mock Interview
| Method | Endpoint | Description |
|---|---|---|
| POST | `/mock/sessions` | Start session, receive first question |
| POST | `/mock/sessions/{id}/answer` | Submit answer → evaluation + next question |
| POST | `/mock/sessions/{id}/end` | End session |
| GET | `/mock/sessions` | List sessions |
| GET | `/mock/sessions/{id}` | Session with all scores |

### Analytics
| Method | Endpoint | Description |
|---|---|---|
| GET | `/analytics/summary` | Overall performance stats |
| GET | `/analytics/topics` | Per-topic performance breakdown |
| GET | `/analytics/weekly-report` | AI-generated weekly insights |
| POST | `/analytics/company-prep` | Generate company-specific prep plan |

---

## WebSocket Protocol

Connect to `ws://localhost:8000/api/v1/transcription/live/{interview_id}?source=system|mic|auto`.

**`source` query parameter:**

| Value | Behavior |
|---|---|
| `system` | Meeting audio (system capture) — heuristic speaker labeling, question detection active |
| `mic` | Microphone only — all segments labeled "candidate", question detection skipped |
| `auto` | Default — same as `system` |

**Client → Server**

```jsonc
// Binary frame: raw audio bytes (webm / opus / mp3)

// Text frame — control messages:
{"type": "flush"}                               // process current buffer immediately
{"type": "manual_question", "question": "..."}  // inject a typed question
{"type": "end"}                                  // save transcript + close session
```

**Server → Client**

```jsonc
{"type": "status",   "message": "Connected. Start speaking."}

{"type": "transcript",
 "speaker": "interviewer",   // or "candidate"
 "text": "Tell me about RAG...",
 "start_time": 12.4, "end_time": 14.1}

{"type": "question_detected",
 "question": {
   "text": "What is RAG?",
   "rewritten_text": "Can you explain how Retrieval-Augmented Generation works?",
   "type": "technical",       // technical | behavioral | system_design | coding
   "topic": "RAG",
   "is_followup": true,
   "timestamp_seconds": 14.1
 },
 "guidance": null}             // null here; guidance arrives in the next two message types

{"type": "guidance_chunk", "text": "**Key points"}  // streamed token-by-token
{"type": "guidance_done"}                            // guidance complete

{"type": "error",   "message": "Transcription failed: ..."}
{"type": "session_closed"}
```

---

## LangGraph Workflows

### `interview_graph` — Batch Transcript Pipeline

```
START
  └─► detect_questions      (Haiku: extract + classify questions)
        └─► analyze_followups   (Haiku: rewrite with context)
              └─► enrich_with_rag  (Sonnet: generate guidance for each question)
                    └─► END
```

### `mock_interview_graph` — Mock Session State Machine

```
START
  └─► generate_question     (Sonnet: ask next company-specific question)
        └─► [await user answer via REST]
              └─► evaluate_answer   (Sonnet: score on 4 dimensions)
                    ├─► generate_question   (if questions_remaining > 0)
                    └─► finalize_session    (if max questions reached)
                          └─► END
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required |
| `OPENAI_API_KEY` | — | Required (Whisper + GPT-4o fallback) |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/interview_copilot` | |
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `PRIMARY_MODEL` | `claude-sonnet-4-6` | Guidance generation |
| `FAST_MODEL` | `claude-haiku-4-5-20251001` | Question detection + follow-up analysis |
| `FALLBACK_MODEL` | `gpt-4o` | LLM fallback |
| `TRANSCRIPTION_BACKEND` | `api` | `api` (OpenAI Whisper) or `local` |
| `VECTOR_STORE_TYPE` | `chroma` | `chroma` (default) or `pinecone` |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | ChromaDB persistence path |
| `UPLOAD_DIR` | `./uploads` | Resume upload directory |

---

## Roadmap

### Phase 1 — Live Interview Core ✅
- [x] WebSocket live audio streaming
- [x] Whisper transcription with speaker labeling
- [x] Haiku question detection with heuristic pre-filter
- [x] Sonnet streaming guidance with resume context
- [x] Sub-2s latency (fast path + background tasks + parallel fetches)
- [x] Mock interview sessions with AI scoring
- [x] Analytics dashboard + weekly AI reports
- [x] Company prep generator (FAQ, skill gap, study plan)
- [x] **Live meeting companion app** (`/companion`) — works with Teams, Meet, Zoom, any platform
- [x] System audio capture via `getDisplayMedia` + meeting audio question detection
- [x] `?source=` WebSocket param for mic / system / auto speaker labeling

### Phase 2
- [ ] Speaker diarization (Pyannote.audio) — more accurate than silence-gap heuristic
- [ ] Next.js frontend with real-time transcript panel
- [ ] Interview knowledge base browser
- [ ] Company-specific question bank with past-interview crowd data

### Phase 3
- [ ] Desktop app (Electron) — no browser needed, captures system audio natively
- [ ] Chrome extension overlay that injects guidance directly into Meet/Teams tabs

---

## License

MIT — see [LICENSE](LICENSE)

---

## Author

**Chandramohan Vardhi** — Generative AI Engineer  
[GitHub](https://github.com/vardhichandra1-dev) · [Email](mailto:vardhichandra1@gmail.com)
