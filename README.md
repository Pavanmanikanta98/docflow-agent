# docflow-agent

[![CI](https://github.com/Pavanmanikanta98/docflow-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Pavanmanikanta98/docflow-agent/actions/workflows/ci.yml)

Document processing pipeline that extracts structured data from invoices and contracts, scores each field against the source text, and holds low-confidence documents for human review before export.

**Demo and walkthrough video:** _coming soon — links added once deployed._

---

## What It Does

Upload a PDF or image → the backend queues it → a LangGraph pipeline extracts text and typed fields → low-confidence documents wait for human review → export as JSON, CSV, or webhook.

```
Invoice / Contract (PDF, PNG, JPEG)
       ↓
  Parse        — PDFs: PyMuPDF → pdfplumber → Tesseract OCR; images: Tesseract OCR
       ↓
  Extract      — LLM call #1: pydantic-ai structured output, one schema per document type
       ↓
  Validate     — LLM call #2: scores each extracted field against the raw text
       ↓
  Route        — score ≥ CONFIDENCE_THRESHOLD → completed, otherwise → awaiting review
       ↓
  Human Review — approve or reject in the UI
       ↓
  Export       — JSON, CSV, or webhook
```

---

## Key Features

- **LangGraph pipeline** — typed shared state and conditional routing (failed / review / completed)
- **Structured extraction** — pydantic-ai validates every LLM output against a typed schema
- **Human-in-the-loop** — documents below the confidence threshold wait for a reviewer
- **OCR fallback** — scanned PDFs fall through to Tesseract; PNG/JPEG uploads go straight to OCR
- **Async processing** — uploads return immediately; an ARQ worker processes the queue
- **Swappable LLM** — Groq by default; OpenAI or Ollama via `LLM_PROVIDER`
- **Evaluation harness** — 32 hand-labelled cases (20 clean, 12 adversarial) scored with deterministic field matchers
- **Plugin architecture** — each document type is one file in `backend/plugins/`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph |
| Structured outputs | pydantic-ai |
| LLM | Groq (OpenAI / Ollama supported) |
| Parsing | PyMuPDF, pdfplumber, Tesseract OCR |
| Backend | FastAPI, ARQ task queue, Redis |
| Database | PostgreSQL (SQLAlchemy, Alembic) |
| Frontend | Next.js, TypeScript, Ant Design |

---

## Evaluation

32 hand-labelled documents in `backend/tests/evaluation/golden/` — 18 invoices, 14 contracts
(prompt injection, letterhead vs Bill-To, invoice total vs account balance, OCR-style
digit noise, negative credit note, five line items across two pages, Italian comma
decimals, milestone-sum contract value, superseding amendment). Scored field by field
with deterministic matchers: numbers within 0.01, dates parsed to the same day, names
fuzzy-matched, null-vs-value checked. No LLM-as-judge. Custom evaluation harness, not DeepEval.

Run on 28 Sep 2026 via Groq (model `openai/gpt-oss-20b`). Results in `evals/results/2026-09-28-openai-gpt-oss-20b.json`.

| Metric | Value |
|---|---|
| Model | openai/gpt-oss-20b |
| Total field checks | 261 |
| Passed | 235/261 (90.0%) |
| Wall clock time | 133.97 s |

**Per-field results**

| Field | Passed / Total | Accuracy |
|---|---|---|
| invoice_number | 18/18 | 100% |
| line_items | 18/18 | 100% |
| currency | 31/32 | 97% |
| due_date | 17/18 | 94% |
| invoice_date | 17/18 | 94% |
| vendor_name | 17/18 | 94% |
| total_amount | 17/18 | 94% |
| subtotal | 12/12 | 100% |
| tax_amount | 11/11 | 100% |
| parties | 13/14 | 93% |
| effective_date | 13/14 | 93% |
| expiry_date | 13/14 | 93% |
| contract_value | 12/14 | 86% |
| jurisdiction | 10/14 | 71% |
| key_obligations | 12/14 | 86% |
| termination_clause | 4/14 | 29% |

**Weakest field: termination_clause (29%)** — free-text extraction where contract changes
are subtle, and deterministic fuzzy matching penalizes reformatting. Candidates for
future improvement: a DeepEval judge (ADR 008) or more training examples.

```bash
# Reproduce: set the model in .env, then
DATABASE_URL=... REDIS_URL=... uv run python -m backend.tests.evaluation.run_eval --model openai/gpt-oss-20b
```

---

## Webhooks

Off by default. Set `WEBHOOKS_ENABLED=true` and `WEBHOOK_SECRET`, then pass `webhook_url`
on upload. DocFlow sends `document.completed` (auto-approved) and `document.approved`
(approved by a reviewer).

- Only `https` URLs whose host resolves to a public IP are accepted; redirects are not followed.
- `X-Idempotency-Key` is the same for every send of the same document + event.
- Verify the signature on your side:

```python
import hashlib, hmac, time

def verify(secret: str, body: bytes, timestamp: str, signature: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:   # reject old or replayed requests
        return False
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return hmac.compare_digest(expected.hexdigest(), signature)
# headers: X-Timestamp -> timestamp, X-DocFlow-Signature -> signature
```

---

## Data Handling

- Uploaded file bytes are kept in Redis for up to 1 hour so the worker can process them,
  then deleted. They are not written to the app's disk or database.
- Extracted fields and review decisions are stored in PostgreSQL.
- With the default Groq provider, document text is sent to the Groq API over HTTPS.
  With `LLM_PROVIDER=ollama`, text stays on your own machine.

---

## Running Locally

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js + pnpm, Docker,
and the `tesseract` binary (for OCR).

```bash
git clone https://github.com/Pavanmanikanta98/docflow-agent
cd docflow-agent

docker compose up -d          # local PostgreSQL + Redis only
cp .env.example .env          # add GROQ_API_KEY and check the other values
uv sync --extra dev
uv run alembic upgrade head

uv run uvicorn backend.api.main:app --reload       # terminal 1 — API on :8000
uv run arq backend.queue.worker.WorkerSettings     # terminal 2 — worker

cd frontend && pnpm install && cp .env.local.example .env.local
pnpm dev                                           # terminal 3 — UI on :3000
```

Tests:

```bash
uv run pytest backend/tests/unit backend/tests/integration -q
```

---

## Built by

Pavan Manikanta — AI engineer
- pydantic-ai contributor (3 merged PRs)
- GitHub: https://github.com/Pavanmanikanta98
