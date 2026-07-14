# CareerForge AI

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=next.js)](https://nextjs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Pytest](https://img.shields.io/badge/pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](https://docs.pytest.org/en/stable/)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)](https://github.com/features/actions)

AI-powered career coaching: resume optimization (SQL + vector hybrid retrieval), cover letters, ATS scoring, application tracking, and mock interviews with Whisper STT.

## Architecture overview

```
┌─────────────┐     JWT      ┌──────────────────┐
│  Next.js UI │ ───────────► │  FastAPI API     │
└─────────────┘              └────────┬─────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
             ┌──────────┐      ┌───────────┐     ┌────────────┐
             │ SQL DB   │      │  Chroma   │     │  LLM APIs  │
             │(SQLite/  │      │ (vectors) │     │ Groq/OpenAI│
             │ Postgres)│      └───────────┘     └────────────┘
             └──────────┘
```

### Why SQL **and** a Vector DB (Chroma)?

| Store | Owns | Interview talking point |
|-------|------|-------------------------|
| **SQL (SQLAlchemy)** | Users, auth hashes, resumes metadata, applications, ATS scores, FKs, constraints | ACID ownership, multi-tenant isolation via `user_id`, indexes for list/filter queries |
| **Chroma (vector)** | Chunked resume embeddings for semantic search | ANN retrieval: “which resume bullets best match this JD?” without full-table scans |

**Hybrid path on optimize:**
1. Load resume row from SQL (authorized by JWT + `user_id`)
2. Query Chroma for top-k chunks filtered by `{user_id, resume_id}`
3. Pass focused evidence + full resume to the LLM
4. Persist tailored result + optional Application row in SQL

## Stack

- **Frontend:** Next.js 16, React 19, Tailwind CSS 4
- **Backend:** FastAPI, SQLAlchemy 2, SQLite (dev) / Postgres-ready
- **Vectors:** Chroma persistent client
- **AI:** LangChain + Groq, OpenAI Whisper / `gpt-4o-transcribe`

## Data model (clean schema)

```
User 1──* Resume 1──* TailoredResume
  │           │
  │           └──* Application
  └──────────────* Application
```

**Constraints & indexes (high-signal for interviews):**
- `ForeignKey(..., ondelete="CASCADE" | "SET NULL")` with SQLite `PRAGMA foreign_keys=ON`
- `CheckConstraint` on `application.status` and ATS score range `0–100`
- Composite indexes: `(user_id, status)`, `(user_id, is_primary)`, `(resume_id, created_at)`, etc.
- ORM `relationship` + `cascade="all, delete-orphan"` for graph clarity

## Security (user data)

| Control | Implementation |
|---------|----------------|
| Password storage | bcrypt (cost 12), never store plaintext |
| Password policy | min 8 chars, letters + numbers |
| Auth | JWT Bearer, exp required, short-lived access tokens |
| Auth abuse | In-memory sliding-window rate limit on `/api/auth/*` |
| Isolation | All queries filter by `current_user.id`; vector queries also filter `user_id` |
| Uploads | Per-user directory, PDF magic-byte check, size cap, sanitized filenames |
| API hygiene | No filesystem paths in list responses; security headers middleware; CORS allowlist |
| Secrets | `.env` only; production refuses weak `SECRET_KEY` |

## Scalability notes

**What scales today (single node):**
- Stateless API processes (horizontal scale behind a load balancer)
- JWT auth → no sticky sessions
- SQLite + WAL for local/dev; switch `DATABASE_URL` to Postgres for multi-writer
- Chroma on local disk for demos; swap for hosted Chroma / pgvector / Pinecone in production

**Recommended production path:**
1. **Postgres** (managed) — connection pool (`DB_POOL_SIZE` / `DB_MAX_OVERFLOW`)
2. **Object storage** (S3/GCS) for PDFs instead of local `uploads/`
3. **Managed vector index** or Postgres `pgvector` to co-locate structured + embeddings
4. **Redis** for distributed rate limiting & job queues (optimize/transcribe async)
5. **Background workers** for Whisper/LLM long jobs (Celery / RQ / Cloud Tasks)
6. **Read replicas** for analytics dashboards once write load grows
7. **CDN** for static Next.js assets; API remains private

**Bottlenecks to call out in interviews:**
- LLM & Whisper latency (I/O bound) → async queue + webhooks/SSE
- Embedding re-index on large resumes → batch offline jobs
- SQLite write lock → not for multi-instance writes

## Database migrations (Alembic)

Production-grade schema changes use **Alembic** (not ad-hoc `migrate.py`).

```bash
cd backend
alembic upgrade head          # apply migrations
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

- **SQLite** is the default for local demos (`DATABASE_URL=sqlite:///./careerforge.db`).
- **PostgreSQL** is production-ready: set  
  `DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/careerforge`  
  then `alembic upgrade head`. Pool settings: `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`.

`Base.metadata.create_all` still runs on startup for empty local DBs; Alembic is the source of truth for schema evolution.

## Hybrid ATS scoring (3 layers)

ATS is **not** an LLM-invented percentage. Scoring is explainable:

| Layer | Type | Cap | What it does |
|-------|------|-----|----------------|
| **1 Rules** | Deterministic | 55 | Keywords, sections, projects, metrics, action verbs, length |
| **2 Semantic** | Chroma vectors | 25 | Cosine similarity of resume chunks vs JD |
| **3 LLM qualitative** | Coaching only | 20 | Bounded 1–10 fit → points; strengths / improvements narrative |

```
Final ATS = Layer1 + Layer2 + Layer3   (0–100)
```

Pipeline: pre-score gaps → LLM rewrite (improved prompt, no fake ATS %) → re-score tailored text.

API: `ats_score`, `layer_scores`, `ats_breakdown`, `matched_keywords`, `missing_keywords`,
`score_before`, `score_delta`, `qualitative_summary`, `strengths`.

Service: `app/services/ats_analyzer.py`

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

## Quick start

### Backend

```bash
# from repo root
.\venv\Scripts\activate   # Windows
cd backend
# .env: SECRET_KEY, GROQ_API_KEY, optional OPENAI_API_KEY
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8002
```

Health (includes DB + vector status): http://127.0.0.1:8002/health  
Docs: http://127.0.0.1:8002/docs

### Frontend

```bash
cd frontend
# .env.local: NEXT_PUBLIC_API_URL=http://127.0.0.1:8002
npm install
npm run dev
```

App: http://localhost:3000

## Environment

`backend/.env` example:

```env
APP_ENV=development
DATABASE_URL=sqlite:///./careerforge.db
SECRET_KEY=generate-a-long-random-string
GROQ_API_KEY=
OPENAI_API_KEY=
CHROMA_ENABLED=true
CHROMA_PERSIST_DIR=./chroma_data
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

## Feature map

| Feature | UI | API |
|--------|----|-----|
| Auth / profile / password | `/auth/*`, `/profile` | `/api/auth/*` |
| Multi-resume management | `/profile` | `/api/resume/*` |
| Optimize + PDF export | `/optimizer` | `/api/optimize` |
| Skill extract from JD | optimizer / applications | `/api/skills/extract` |
| Application tracker | `/applications` | `/api/applications` |
| Analytics dashboard | `/dashboard` | `/api/analytics/summary` |
| Interview Q bank + Whisper | `/interview` | `/api/interview/*` |

## Project layout (backend)

```
backend/app/
  models/models.py      # schema, FKs, indexes, relationships
  core/database.py      # engine, FK pragma, pools
  core/security.py      # bcrypt, JWT, ownership helpers
  core/middleware.py    # security headers + auth rate limit
  services/vector_store.py  # Chroma hybrid retrieval
  routers/              # thin HTTP layer
```
