# RULES.md — Project Rules for docflow-agent

Single source of truth for all AI agent rules in this repository.
Imported by CLAUDE.md and GEMINI.md.
Do not duplicate these rules anywhere else.

---

## The One Rule That Overrides Everything

Before making any architectural decision, adding a dependency, changing folder structure, or modifying the database schema — present your reasoning and wait for confirmation.

Format your ask like this:
1. What you want to do
2. Why you think it is needed
3. What the trade-offs are
4. Whether it aligns with the scalability principles in DECISIONS.md

Do not ask a bare "should I do X?" — always bring the reasoning.
Once confirmed, proceed without asking again for the same decision.

---

## Never Do These Without Explicit Confirmation

- Add a new `pip install` or `npm install` dependency
- Change the database schema (add/remove/rename columns or tables)
- Change the folder structure
- Add a new document type to the pipeline
- Change the LLM provider or model name
- Modify the queue configuration
- Change environment variable names (breaks deployed config)
- Delete any file
- Modify `DECISIONS.md` — that file is a log, not working code

---

## Always Do These Without Being Asked

- Add type hints to every function you write
- Run `pytest` after any backend change and report results
- Keep functions small — if a function exceeds 30 lines, question whether it should be split
- Use `config.py` for any value that could vary by environment — never hardcode
- Write the test before the implementation for pure functions (parsers, validators, models, utils)
- Write tests alongside implementation for LangGraph nodes

---

## Code Style

**Python (backend):**
- Type hints on every function — parameters and return types
- Formatter: `black` (line length 88)
- Linter: `ruff`
- No `import *` anywhere
- Imports ordered: stdlib → third-party → local
- No hardcoded strings in business logic — use constants or config

**TypeScript (frontend):**
- Strict mode on
- No `any` types
- Component files: PascalCase (`DocumentUploader.tsx`)
- Utility files: camelCase (`formatExtraction.ts`)

---

## Testing Rules

**Unit tests (runs every commit):**
- Use `pydantic_ai.models.test.TestModel` for all LLM calls — no real API calls in unit tests
- Test behaviour, not implementation — test what a function does, not how
- Every new pure function (parser, validator, model, util) must have a test before the implementation

**Integration tests (runs every commit):**
- Full pipeline with mocked LLM via TestModel
- Cover happy path + at least one failure case per agent

**Evaluation tests (run on demand only):**
- DeepEval suite — real LLM calls, measures extraction accuracy
- Do not run in CI by default — they cost API credits

If you write code with no test, flag it explicitly: "This function has no test — confirm this is acceptable."

---

## Architecture Rules

These come from DECISIONS.md. Enforce them on every change.

**LLM is always swappable**
Never call `groq.client.chat()` directly in business logic. Always go through the `LLMClient` abstraction in `backend/core/llm.py`. If it does not exist yet, create it before writing any agent code.

**No synchronous document processing**
Documents are never processed in a FastAPI request handler directly. Upload → ARQ job → worker processes. If you find yourself calling agent pipeline code inside a route handler, stop and restructure.

**tenant_id on every DB table**
Every model that stores data must have a `tenant_id` field. No exceptions. Even if the demo uses only one tenant.

**Config from environment only**
If a value could change between local dev, staging, and production — it lives in `.env` and is loaded via `config.py`. Never inline in code.

**Document types as plugins**
New document types go in `backend/plugins/`. Each plugin implements the `DocumentPlugin` interface. Core pipeline code must not change when a new document type is added.

---

## Folder Structure (do not change without confirmation)

```
docflow-agent/
├── backend/
│   ├── agents/          # LangGraph agent nodes
│   ├── core/            # LLMClient, config, shared utilities
│   ├── plugins/         # Document type plugins (invoice, contract)
│   ├── api/             # FastAPI routes
│   ├── models/          # Pydantic models and DB models
│   ├── queue/           # ARQ worker and job definitions
│   └── tests/           # pytest tests
├── frontend/            # Next.js 16, App Router, TypeScript, Tailwind v4
│   ├── app/             # App Router — pages live here, not pages/
│   ├── components/      # React components
│   └── lib/             # API client, shared types
├── DECISIONS.md
├── RULES.md
├── CLAUDE.md
├── GEMINI.md
├── DEVELOPER_GUIDE.md
└── README.md
```

---

## When You Are Unsure

Check `DECISIONS.md` first.
If DECISIONS.md does not answer it, present your reasoning and ask.
Never assume. Never guess at architecture.
