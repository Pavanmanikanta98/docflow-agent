# docflow-agent — Project Decisions Log

All architectural and product decisions made before writing a single line of code.
This is the source of truth. When in doubt, refer here.

---

## Product Scope

| Decision | Choice | Reason |
|---|---|---|
| Document types at launch | Invoices + Contracts | Focused enough to finish in 4 weeks, two types proves plugin architecture works |
| Output formats | JSON + CSV + Webhook | JSON for programmatic use, CSV for business users, Webhook for integrations |
| Auth | API key per client | One day to implement, signals production thinking, supports multi-tenant naturally |
| Upload mode | One at a time (UI) — batch-ready (backend API accepts array) | Clean demo, no rewrite needed when client asks for batch |

---

## Tech Stack

| Layer | Decision | Reason |
|---|---|---|
| Agent orchestration | LangGraph | Stateful graph, conditional routing, native HITL interrupt/resume |
| Structured output | pydantic-ai | Contributor-level usage, TestModel for mocking in tests |
| LLM | Groq default — swappable via env | Free tier, fast inference, one env var switches to Ollama/OpenAI. Default model: `llama-3.1-8b-instant` (speed/volume). Swap to `llama-3.3-70b-versatile` for quality (1k req/day limit) |
| Document parsing | PyMuPDF + pdfplumber + Tesseract OCR | PDF text + image-based documents |
| Frontend | Next.js + TypeScript | React ecosystem, Vercel deployment, rare skill among AI devs |
| Backend | FastAPI | Async, type-safe, Pydantic native |
| Database | PostgreSQL (Neon DB — free tier) | Handles concurrent queue writes, multi-tenant JSON columns, 3GB free |
| Queue library | ARQ | Async Python queue, Redis-backed, lightweight vs Celery |
| Queue backend | Upstash Redis (free tier) | 10k commands/day free — ARQ connects to this |
| Repo structure | Monorepo (`frontend/` + `backend/`) | One link on Upwork, Claude Code sees full context, shared types |
| Evaluation | DeepEval | Behavioral accuracy tests — runs on demand, not on every commit |

**Note:** ARQ is the Python library. Upstash is the hosted Redis that ARQ connects to. They are not alternatives — they work together.

---

## Deployment

| Layer | Platform | Cost | Notes |
|---|---|---|---|
| Frontend | Vercel | Free | Vercel built Next.js, natural home |
| Backend | Render | Free | Cold start issue — fix with UptimeRobot free ping every 5 min |
| PostgreSQL | Neon DB | Free | 0.5GB per project, scale-to-zero |
| Redis | Upstash | Free | 500K commands/month (not daily) — sufficient for portfolio |

**Upgrade path:** First $200-300 from Upwork client → move backend to Railway $5/month. No cold starts, proper uptime.

**UptimeRobot note:** Free tier (50 monitors, 5-min intervals) is restricted to personal use — fine for portfolio. If client requires SLA monitoring, upgrade to paid.

---

## Architecture Principles (Non-Negotiable)

These are scalability decisions made from day one. No exceptions.

**1. LLM backend is swappable**
One `LLMClient` abstraction. Switch Groq → Ollama → OpenAI via `LLM_PROVIDER` env variable. Zero code change required.

**2. Queue-based async processing**
No document processing inline in FastAPI requests. Upload → job into ARQ queue → worker processes async → client polls or receives webhook.

**3. Multi-tenant isolation from day one**
Every DB table has `tenant_id`. Even if day one is single user, the column exists. Never retrofit tenant isolation.

**4. Nothing hardcoded**
No magic numbers, no inline model names, no hardcoded thresholds. Everything in `config.py` loaded from `.env`.
- Confidence threshold → `CONFIDENCE_THRESHOLD=0.75`
- Model name → `LLM_MODEL=llama-3.1-8b-instant`

**5. Document types as plugins**
No `if doc_type == "invoice":` chains in core code. Each document type is a module implementing a standard interface. Adding a new type = adding one file, zero changes to core pipeline.

**6. Tests test behaviour, not implementation**
Refactors and scaling changes must not break the test suite. Test the contract (what a function does), not the internals (how it does it).

---

## TDD Approach

| Code type | Approach |
|---|---|
| Parsers, validators, Pydantic models, config, utils | Strict TDD — write failing test first, then code |
| LangGraph nodes, agent orchestration | Test-alongside — design interface, write test + code together |
| Full pipeline (Parser → Extractor → Validator) | Integration test after each agent is complete |

**Testing layers:**

| Layer | Tool | Runs when | What it tests |
|---|---|---|---|
| Unit tests | pytest + pydantic-ai TestModel | Every commit | Pure functions, schema validation, no real LLM calls |
| Integration tests | pytest | Every commit | Full pipeline with mocked LLM |
| Evaluation | DeepEval (20+ cases) | On demand / nightly | Behavioral accuracy — is extracted value correct? |

**pydantic-ai TestModel:** Use this to mock all LLM calls in unit and integration tests. No API cost, deterministic, fast.

---

## Privacy and Security

Decisions that must be built in from day one — not added later.

| Concern | Decision |
|---|---|
| Document storage | Processed in-memory only. Never written to disk after upload |
| LLM data exposure | Groq by default (third-party API). Ollama option for self-hosted clients |
| Transport | HTTPS only (Render + Vercel both enforce this) |
| Audit log | Log filename, timestamp, doc type — never log document content |

**Tiered client response:**
- SMB clients: Groq + HTTPS + in-memory processing
- Privacy-conscious clients: Ollama local deployment option (1 env var switch)
- GDPR / self-hosted: Full Docker Compose package, runs on client's own server

---

## Agent Pipeline

```
Document Upload
      ↓
Agent 1 — Parser       (extract raw text, identify document type)
      ↓
Agent 2 — Extractor    (pydantic-ai structured fields: amounts, dates, parties, line items)
      ↓
Agent 3 — Validator    (confidence scoring per field)
      ↓
HITL Layer             (low-confidence fields surface in UI for human review)
      ↓
Export                 (JSON + CSV + Webhook)
```

---

## What Was Rejected and Why

| Idea | Rejected because |
|---|---|
| Sequential Python functions for orchestration | No state management, no conditional routing, not scalable |
| SQLite | Concurrent queue workers cause write lock issues |
| Render free tier without UptimeRobot | 30-60 second cold starts kill demo impressions |
| Railway from day one | No permanent free tier — minimum $5/month |
| Celery for queue | Heavier than ARQ, overkill for this project |
| Split frontend/backend repos | Two links, more overhead, Claude Code loses context |
