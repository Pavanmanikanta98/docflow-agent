# Repository Guidelines

## Project Structure & Module Organization
`backend/` contains the FastAPI API, queue workers, agent pipeline, plugins, models, and tests. Key areas are `backend/api/` for routes, `backend/core/` for config and pipeline code, `backend/agents/` for parser/extractor/validator logic, and `backend/tests/` for `unit`, `integration`, and `evaluation` suites. `frontend/` is a Next.js app: `app/` holds routes, `components/` contains UI pieces, `lib/` stores shared types and API helpers, and `public/` holds static assets. Database migrations live in `alembic/`.

## Build, Test, and Development Commands
Backend setup:
```bash
uv venv && source .venv/bin/activate
uv pip install -e .[dev]
uvicorn backend.api.main:app --reload
python -m backend.queue.worker
```
Use `docker-compose up` to start local Postgres and Redis. Run backend tests with `pytest` and add coverage with `pytest --cov=backend`. Frontend setup:
```bash
cd frontend
pnpm install
pnpm dev
pnpm build
pnpm lint
```

## Coding Style & Naming Conventions
Python targets 3.11 with Black and Ruff configured for an 88-character line length. Use 4-space indentation, `snake_case` for functions/modules, `PascalCase` for Pydantic models and classes, and keep FastAPI route handlers type-annotated. TypeScript and React files use 2-space indentation in the current codebase, `PascalCase` for components, and colocated route files under `frontend/app/` such as `app/review/[id]/page.tsx`.

## Testing Guidelines
Pytest is configured in `pyproject.toml` with `backend/tests` as the test root and `asyncio_mode = auto`. Name tests `test_*.py` and mirror the code area under test when possible, for example `backend/tests/unit/test_placeholder.py`. Put quick deterministic checks in `unit/`, API and storage flows in `integration/`, and extraction-quality benchmarks in `evaluation/`.

## Commit & Pull Request Guidelines
Recent history uses short Conventional Commit subjects like `feat: initialize project structure...`; continue with prefixes such as `feat:`, `fix:`, `refactor:`, and `docs:`. Keep each commit scoped to one concern. PRs should include a concise summary, linked issue or task, test evidence (`pytest`, `pnpm lint`, screenshots for UI changes), and note any schema, env, or migration impact.

## Configuration & Security Tips
Keep secrets in local env files and out of git. Use Docker or local services for Postgres and Redis during development, and review Alembic migrations before applying them to shared environments.
