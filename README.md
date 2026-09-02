# docflow-agent

Multi-agent document processing pipeline that extracts structured data from invoices and contracts, validates confidence, and routes low-confidence fields to human review before export.

**Demo and walkthrough video:** _coming soon — links added once deployed._

---

## What It Does

Upload a business document → agents extract structured fields → low-confidence extractions are flagged for your review → export clean data as JSON, CSV, or webhook.

```
Invoice / Contract
       ↓
  Parser Agent       — identifies document type, extracts raw text
       ↓
 Extractor Agent     — pulls structured fields (amounts, dates, parties, line items)
       ↓
 Validator Agent     — scores confidence per field
       ↓
  Human Review       — low-confidence fields surface in UI for approval
       ↓
    Export           — JSON, CSV, or webhook to your system
```

---

## Key Features

- **Multi-agent orchestration** — LangGraph stateful pipeline with conditional routing
- **Structured extraction** — pydantic-ai validates every output against typed schemas
- **Human-in-the-loop** — uncertain fields pause the pipeline and surface for review
- **Swappable LLM** — Groq by default, switch to Ollama for fully local processing (one env variable)
- **Evaluation suite** — DeepEval test suite with 20+ cases and accuracy metrics
- **Plugin architecture** — add new document types without touching core pipeline code

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph |
| Structured outputs | pydantic-ai |
| LLM | Groq (swappable to Ollama) |
| Backend | FastAPI + ARQ (async queue) |
| Frontend | Next.js + TypeScript |
| Database | PostgreSQL (Neon) |
| Queue | ARQ + Upstash Redis |

---

## Extraction Accuracy

Accuracy is measured with the in-repo evaluation suite (`backend/tests/evaluation/`):
10 gold-standard invoices and 10 gold-standard contracts, scored field-by-field
against the real LLM. Run on demand — see `evaluation_walkthrough.md`.

Fields scoring below `CONFIDENCE_THRESHOLD` (default 0.75) are automatically
flagged for human review before export.

> Live accuracy numbers will be published here once the demo is deployed and
> the eval suite has been run against the production model and prompts.

---

## Data Privacy

Documents are processed in-memory and never written to disk.

| Deployment mode | How it works |
|---|---|
| Cloud (default) | Text sent to Groq API over HTTPS. Not stored after processing. |
| Local (Ollama) | Set `LLM_PROVIDER=ollama`. Documents never leave your infrastructure. |
| Self-hosted | Full Docker Compose. Runs entirely on your servers. |

---

## Running Locally

```bash
git clone https://github.com/Pavanmanikanta98/docflow-agent
cd docflow-agent

# Backend
cd backend
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env   # add your keys

# Frontend
cd ../frontend
pnpm install
cp .env.local.example .env.local

# Start
uvicorn api.main:app --reload   # terminal 1
python -m arq queue.worker.WorkerSettings   # terminal 2
pnpm dev   # terminal 3, inside frontend/
```

---

## Docker (one command)

```bash
docker-compose up
```

Frontend: http://localhost:3000
Backend: http://localhost:8000/docs

---

## Built by

Pavan Manikanta — AI agent developer
- pydantic-ai contributor (3 merged PRs: SambaNova + Alibaba providers)
- GitHub: https://github.com/Pavanmanikanta98
