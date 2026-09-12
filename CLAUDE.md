# CLAUDE.md — docflow-agent

Read this first in every Claude Code session. Then read `SPRINT.md`.

@RULES.md
@SPRINT.md

---

## What this project is

An async document-extraction pipeline for invoices and contracts:
upload (FastAPI) → queue (ARQ + Redis) → parse (PyMuPDF → pdfplumber → Tesseract OCR)
→ extract (pydantic-ai, structured output) → validate (second LLM pass + deterministic checks)
→ route (auto-complete or human review) → export (JSON / CSV / signed webhook).
Frontend: Next.js 16 + TypeScript. DB: PostgreSQL. Orchestration: LangGraph.

**Why it exists:** portfolio proof for AI engineer interviews (India, 2026). It must be
live, tested, measured and honest. It is NOT a commercial product right now.

## Current goal: Ship v1 (see SPRINT.md → "Current sprint")

Done means: live URL, a 3-minute Loom, green CI, a published eval table with real
numbers, and a README where every claim can be pointed at in the code.

**Out of scope until an offer or a paying client:** vendor resolution, duplicate
detection, audit logs, login/NextAuth, bounding-box review UI, ERP connectors,
multi-tenant SaaS features. If a task drifts into these, stop and say so.

## Hard rules for Claude in this repo

1. **No invented numbers.** Never write an accuracy %, time saved, document volume or
   cost figure unless it comes from a file in `evals/results/` or a measured log. If a
   number is unknown, write "not measured yet".
2. **One task per branch.** Branch names: `fix/…`, `feat/…`, `chore/…`, `docs/…`
   (e.g. `fix/invoice-math-gate`). Never commit to `main` directly.
3. **Every behaviour change comes with a test** that fails before the change and passes
   after. Unit tests use `pydantic_ai.models.test.TestModel` or `FunctionModel`; no real
   LLM calls outside `backend/tests/evaluation/`.
4. **Before you say "done":** run `uv run pytest backend/tests/unit backend/tests/integration -q`
   and `uv run ruff check backend`, paste the summary, and list the files changed.
5. **Stop and ask** before: adding a dependency, changing the DB schema, deleting files,
   changing env var names, or changing the LLM model (RULES.md applies).
6. **Keep SPRINT.md true.** Tick the task you finished, add anything you discovered under
   "Open polish", and never mark a task done if a test is missing.
7. The evaluation suite is a **custom deterministic harness** (pytest + golden JSON +
   fuzzy/number/date matchers in `backend/tests/evaluation/conftest.py`). It does not
   use DeepEval. Describe it that way in docs.

## Useful commands

```bash
docker compose up -d                      # local Postgres + Redis
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn backend.api.main:app --reload
uv run arq backend.queue.worker.WorkerSettings
uv run pytest backend/tests/unit backend/tests/integration -q
uv run pytest backend/tests/evaluation -s   # real LLM calls, costs credits
cd frontend && pnpm dev
```

## Where other notes live

- `DECISIONS.md` — original architecture log (do not edit; add superseding notes in
  `ARCHITECTURE_DECISIONS.md`).
- Career/resume notes about this project are outside the repo, in Pavan's
  `mindMap/career/claude-coach/` folder. Do not copy business plans or resume text
  into this public repo.
