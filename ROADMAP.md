# docflow-agent — Build Roadmap
> Goal: Working demo live → Upwork portfolio ready

**One rule: each phase has one outcome. Don't start the next phase until that outcome works.**

---

## Current State (April 2026)

Phases 1–6 scaffolded and partially implemented. Gap analysis revealed deviations from DECISIONS.md.
Proceeding with Option A — fix deviations, then move to frontend.

### What exists and is good
- DB models (`db.py`) — clean, proper enums, correct nullable fields
- Schemas (`schemas.py`) — mostly good, one cleanup needed
- Config (`config.py`) — clean pydantic-settings
- API structure (`main.py`, `routers/`) — working
- Queue setup (`worker.py`) — working but has a hardcoded value
- Extractor agent — working

### What is missing or wrong
- `backend/core/pipeline.py` — LangGraph graph never created (key differentiator)
- `backend/agents/validator.py` — doesn't exist, confidence is LLM self-reported only
- `backend/api/middleware.py` — API key auth not implemented
- `WEBHOOK_TIMEOUT_SECONDS` — hardcoded as `10` in worker.py instead of from config
- `DocumentExportRequest` — still has junk fields
- Tests — folders exist, all empty
- Plugin architecture — empty stubs, not wired to pipeline

---

## Fix Phase — Option A (Do This First)

Fix in this exact order. Each fix is small and standalone.

### Fix 1 — Config leak `(15 min)`
**File:** `backend/queue/worker.py`
Remove hardcoded `10`. Use `settings.webhook_timeout_seconds` instead.

**Done when:** No magic numbers in worker.py.

---

### Fix 2 — Schema cleanup `(20 min)`
**File:** `backend/models/schemas.py`
Clean `DocumentExportRequest` — remove `export_size`, `export_mime_type`,
`export_results`, `export_confidence_score`, `export_human_review_*`.
Keep only: `job_id` + `format`.

**Done when:** `DocumentExportRequest` has exactly 2 fields.

---

### Fix 3 — LangGraph pipeline `(2 days)`
**File:** `backend/core/pipeline.py` ← create this

This is the most important fix. LangGraph is the Upwork differentiator.
Without it, this is just another Python backend. With it, you're building
stateful agent pipelines — a rare skill.

**The graph:**
```
parse → extract → validate →
    confidence >= 0.75 → status = completed
    confidence <  0.75 → status = awaiting_review
```

**Start here — write this first:**
```python
from typing import TypedDict, Optional

class PipelineState(TypedDict):
    document_id: int
    raw_text: str
    extracted_fields: Optional[dict]
    confidence_score: Optional[float]
    status: str
```

Then build one node at a time. Don't write the whole graph at once.

**Done when:** You can call the pipeline with raw text and it returns a status.

---

### Fix 4 — Validator `(1 day)`
**File:** `backend/agents/validator.py` ← create this

Real per-field confidence scoring. Not LLM self-reported.
Each extracted field gets a score: is the value plausible for this field type?

**Done when:** Validator returns a score per field, not just one overall score.

---

### Fix 5 — API key middleware `(30 min)`
**File:** `backend/api/middleware.py` ← create this

Checks `X-API-Key` header on every request against `settings.api_key`.
Returns 401 if missing or wrong.
~20 lines. No excuses for skipping this — it signals production thinking to clients.

**Done when:** Requests without a valid API key return `401 Unauthorized`.

---

### Fix 6 — 3 tests `(1 day)`
**Folder:** `backend/tests/`

Write these yourself. Not AI-generated. Three tests only:
1. Config loads correctly from `.env`
2. Extractor returns a valid schema (use pydantic-ai TestModel — no real LLM call)
3. Upload endpoint returns a document_id

**Done when:** `pytest` runs and 3 tests pass.

---

## Build Phase — Frontend

Start only after all 6 fixes are done.

### Phase 7 — Can someone see it? `(Day 4–8 after fixes)`

**Outcome:** Visual demo a client can watch without touching the terminal.

```
frontend/app/
  ├── page.tsx               → upload form (drag + drop PDF)
  ├── documents/page.tsx     → document list with live status polling
  └── review/[id]/page.tsx   → approve / reject buttons
```

**Done when:** Full flow works in the browser.
Upload → processing → awaiting review → approve → completed. No terminal needed.

---

### Phase 8 — Is it live? `(Day 9–11 after fixes)`

**Outcome:** Public URL + Loom video = Upwork portfolio ready.

```
Render free tier  → backend (FastAPI + ARQ worker)
Vercel            → frontend (Next.js)
UptimeRobot       → ping every 5 min (prevent cold starts on Render free tier)
Loom recording    → 3 min demo: upload invoice → extracted fields → review → export
```

**Done when:** Anyone can open the URL, upload an invoice, and see structured results.
This URL + Loom goes directly into the Upwork profile.

---

## 3 Mental Rules

**1. Outcome first, not tasks.**
Don't think "I need to write X file."
Ask: "what is the outcome of this fix/phase?" Work backwards from the outcome.

**2. Run it at the end of every session.**
Code that doesn't run doesn't count.
If it doesn't start cleanly when you close VS Code, you haven't finished.

**3. Stuck = step is too big.**
Break it in half.
"Write the LangGraph pipeline" → "Write the PipelineState class" first.
The smallest thing that runs is always the right starting point.

---

## Status Tracker

### Fix Phase
| Fix | What | Status |
|---|---|---|
| 1 | Remove hardcoded timeout in worker.py | `[ ] not started` |
| 2 | Clean DocumentExportRequest schema | `[ ] not started` |
| 3 | LangGraph pipeline in core/pipeline.py | `[ ] not started` |
| 4 | Validator with per-field confidence scoring | `[ ] not started` |
| 5 | API key middleware (401 on bad key) | `[ ] not started` |
| 6 | 3 passing tests written by hand | `[ ] not started` |

### Build Phase
| Phase | What | Status |
|---|---|---|
| 7 | Frontend demo works in browser | `[ ] not started` |
| 8 | Live URL + Loom video ready | `[ ] not started` |

---

## Why LangGraph Matters for Upwork

Most AI devs on Upwork use:
- Plain Python functions chained together
- LangChain with basic sequential chains
- No state management between steps

You will use:
- LangGraph stateful graph with conditional routing
- HITL interrupt/resume built into the graph
- pydantic-ai for structured extraction (contributor-level usage)

React + LangGraph + pydantic-ai contributions = rare combination.
That is the differentiator in proposals. Don't skip it.
