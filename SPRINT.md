# Sprint Planner — docflow-agent

Single source of truth for what is in flight, what is deferred, and what is
parked. Update each entry as it lands.

**How to run a task with Claude Code** (paste into a fresh session in this repo):

```text
Read CLAUDE.md and SPRINT.md. Do task V1-<n> only.
First: git checkout main && git pull && git checkout -b <branch from the task>.
Show me your plan (files + tests) before editing. Write the failing test first.
When finished: run unit + integration tests and ruff, paste results,
tick the task in SPRINT.md, and list anything you found under "Open polish".
Do not merge. I review the diff and open the PR myself.
```

---

## Current sprint — Ship v1 (target: 27 Sep 2026, about 17 hours)

**Goal:** a live, tested, measured, honest demo that holds up when an interviewer
opens the repo or asks "how did you measure that?".

**Order matters.** V1-0 to V1-6 must be done before the URL is public, because the
current code exposes other visitors' documents and allows server-side requests to
any URL.

### Status — 11 Sep 2026 (night)

Code for V1-0 through V1-5 is written as stacked commits.
V1-6 to V1-9 below are written up as implementation sketches, not code yet. **Not ticked yet:** the full unit + integration suite, ruff,
`uv lock` and `docker build` have not been run. Tick each task only after that run
is green on Pavan's machine.

Checked so far (cloud sandbox, stand-ins where packages were unavailable): parser
routing + PNG OCR tests pass; all 17 webhook unit tests pass; the README signature
snippet verifies against `connectors.sign`.

Decisions taken while implementing (Pavan: adding is OK, deleting is not):
- **V1-3** keeps the `X-LLM-Key` feature but puts it behind `ALLOW_USER_LLM_KEY`
  (default `false`) instead of deleting it. Found on the way: any junk value in that
  header skipped all rate limits.
- **V1-5** adds `WEBHOOKS_ENABLED` (default `false`) and `WEBHOOK_SECRET`.
  Header names are unchanged.
- **V1-4** gates on `subtotal + tax = total` (new optional invoice fields) instead of
  summing line-item amounts that never existed, records why a document is held
  (`math_mismatch`, `low_confidence:0.62`) and shows it on the review screen. The LLM
  now returns only scores — it can no longer set the pipeline status itself.
- Nothing was deleted. Candidates for removal are listed under
  "Proposed removals" below for Pavan to approve.

### Schedule — now to release (fits around Saatwika work + 15 applications/week)

About 1 hour on weekday evenings, 3 hours on weekend days. Job applications come first
each day; DocFlow gets the time after.

| Date | Task(s) | Time | Done when |
|---|---|---|---|
| Sat 12 Sep | V1-0 repo hygiene · V1-1 deps + Dockerfile · V1-2 image uploads | 3 h | `docker build` works, OCR + image tests green |
| Sun 13 Sep | V1-3 remove key header · V1-4 math gate | 3 h | 4 new gate/routing tests green |
| Mon 14 Sep | V1-8 CI (so every later PR is checked) | 45 min | CI green on a PR |
| Tue 15 – Wed 16 Sep | V1-5 webhooks + SSRF guard | 2 h | signature, retry-key and SSRF tests green |
| Thu 17 – Fri 18 Sep | V1-6 demo session isolation | 1.5 h | cross-session 404 tests green |
| Sat 19 Sep | V1-7 metrics + eval runs on 2 models | 2.5 h | 2 files in `evals/results/`; fill resume numbers |
| Sun 20 Sep | V1-9 deploy + browser smoke test | 3 h | live URL passes all 5 smoke checks |
| Mon 21 – Fri 25 Sep | Buffer: fix whatever the smoke test found (Open polish) | ≤ 3 h | no open blocker |
| Sat 26 Sep | V1-10 README, diagram, Loom | 2 h | README claims all link to code or results |
| **Sun 27 Sep** | **Release v1.0.0** (checklist below) | 1 h | tag + GitHub Release published |

If a day slips, move the row, not the order. If you are more than 3 days behind on
23 Sep, cut V1-7's second model run, not tests or V1-6.

### Release checklist — v1.0.0 (Sun 27 Sep)
- [ ] All V1 tasks ticked; CI green on `main`; no open blocker in "Open polish".
- [ ] Live URL works from a fresh browser + phone; first-load delay noted in README.
- [ ] README numbers match the files in `evals/results/`.
- [ ] `git tag v1.0.0 && git push --tags`; GitHub Release notes: what it does, links
      (live, Loom), eval table, known limitations, what's deferred.
- [ ] Pin the repo on GitHub; add live + video links to the resume project line.
- [ ] Move this sprint to "Past sprints". Feature work stops here.

### V1-0 · Repo hygiene — `chore/repo-hygiene` — 30 min
- [ ] `git stash list`; `git stash show --include-untracked --name-only stash@{0}`.
      Recover `ROADMAP.md`, `ARCHITECTURE_AUDIT.md`, `MARKET_ANALYSIS.md` if present.
- [ ] Move `BUSINESS_PLAN.md`, `ROADMAP.md`, `ARCHITECTURE_AUDIT.md`,
      `MARKET_ANALYSIS.md` out of the repo (private notes folder). They contain claims
      the code does not support ("SOC-2 ready", audit logs, $150k roles).
- [ ] README: replace "DeepEval test suite with 20+ cases and accuracy metrics" with
      "deterministic evaluation harness: 20 golden cases (10 invoices, 10 contracts)".
      Remove the `docker-compose up` → frontend/backend claim (compose only runs
      Postgres + Redis). Fix the pydantic-ai line to "3 merged PRs".
- **Done when:** repo root has only code + honest docs; tests still green.

### V1-1 · Make it installable and deployable — `fix/ocr-deps-dockerfile` — 1.5 h
- [ ] `backend/agents/parser.py` imports `pytesseract`, but it is not in
      `pyproject.toml` or `requirements.txt` (Pillow only arrives indirectly through
      pdfplumber). A fresh install crashes the worker on import. Declare `pytesseract`
      and `pillow` explicitly (confirm with Pavan first — RULES.md).
- [ ] Add `backend/Dockerfile` (python 3.12 slim + `apt-get install tesseract-ocr`),
      used by both the API and the worker.
- [ ] Unit test: parser returns text for a tiny generated scanned-style PDF (image-only
      page) — skip with a clear reason if the tesseract binary is missing.
- **Done when:** `docker build` works and the OCR test passes inside the container.

### V1-2 · Image uploads actually work — `fix/image-upload-parsing` — 45 min
- [ ] Upload accepts `image/png` and `image/jpeg`, but the parser always opens bytes
      with `fitz.open(..., filetype="pdf")`, so every image upload fails.
      Pass the MIME type into the pipeline; send images straight to Tesseract.
- [ ] Tests: PNG bytes → OCR path is used; PDF bytes → PyMuPDF path is used.

### V1-3 · Close the hidden BYOK path — `fix/llm-key-header-gate` — 1 h
- [ ] Gate `X-LLM-Key` handling (middleware bypass, upload route, `_resolve_model`)
      behind `ALLOW_USER_LLM_KEY=false`. Deleting the code is a proposed removal.
- [ ] `backend/core/llm.py` writes the key into `os.environ` on every call, making it
      process-wide (a user key stays there if no server key is set). Build the
      Groq/OpenAI model with an explicit provider object instead — no env mutation.
- [ ] Test: building a model does not change `os.environ`.

### V1-4 · Fix the invoice math gate — `fix/invoice-math-gate` — 2 h
Current bug: `InvoiceFields.line_items` is `list[str]` and there is no `tax_amount`,
so the gate sums 0 and sends almost every invoice with line items to review.
The validator's `status` is also ignored by `route_after_validate`.
- [ ] Add optional `subtotal` and `tax_amount` to `InvoiceFields` (keep `line_items`
      as strings — the eval suite depends on that shape).
- [ ] Gate: if `subtotal`, `tax_amount` and `total_amount` are all present and
      `abs(subtotal + tax_amount - total_amount) > 0.01` → force review and record
      the reason. If any is missing → skip the gate (do not punish missing data here).
- [ ] Record why a document went to review, e.g.
      `extraction_results["_review_reasons"] = ["math_mismatch"]` or
      `["low_confidence:0.62"]`, and show it on the review screen.
- [ ] Tests (pure function + routing with `TestModel`/`FunctionModel`):
      math OK → gate passes; mismatch → awaiting_review with reason;
      missing subtotal → gate skipped; low confidence → review with reason.
- [ ] Add `subtotal`/`tax_amount` to golden invoices where the input text has them.

### V1-5 · Webhooks: safe and actually idempotent — `fix/webhook-signing-ssrf` — 2 h
- [ ] Idempotency key is `uuid4()` per send, so retries look like new events.
      Use `f"doc-{document_id}-{event}"`.
- [ ] Sign `f"{timestamp}.{body}"` (so the timestamp can't be replayed with a new body);
      secret from `settings` (no `"dummy_secret"` default); timeout from
      `settings.webhook_timeout_seconds`; log failures instead of `print`.
- [ ] SSRF guard: `webhook_url` comes from a public form. Allow `https` only and reject
      hosts resolving to private, loopback or link-local IPs. Add `WEBHOOKS_ENABLED`
      (default `false` on the public demo).
- [ ] Tests: signature verifies with the documented recipe; retry sends the same key;
      `http://127.0.0.1`, `http://169.254.169.254` and `https://10.0.0.5` are rejected.
- [ ] README: a 6-line "verify our webhook signature" snippet.

### V1-6 · Demo isolation without login — `fix/demo-session-isolation` — 1.5-2 h

**Problem.** Every visitor uploads as `tenant_id=demo-tenant-id` (hardcoded in
`DocumentUploader.tsx:31` and `documents/page.tsx:21`), and `GET /documents/{id}`,
`/{id}/file`, `/{id}/export` and `POST /{id}/review` never check the tenant at all.
Anyone can list, read, export and approve anyone else's document.

**Approach.** The browser already creates a stable id (`getSessionId()` in
`frontend/lib/api.ts`) and sends it on every request as `X-Session-Id`. Use that as
the tenant id server-side, and stop accepting a tenant from the query string or form,
so a caller cannot name someone else's tenant.

**Files**
- `backend/api/deps.py` — new `get_tenant_id(request) -> str`: read `X-Session-Id`,
  400 when missing or shorter than 8 characters.
- `backend/api/routes/documents.py` — upload takes the tenant from the dependency
  (drop the `tenant_id` form field); list/get/file filter by it and 404 on mismatch.
- `backend/api/routes/review.py`, `export.py` — same dependency, 404 on mismatch.
- `frontend/components/DocumentUploader.tsx`, `app/documents/page.tsx`,
  `app/review/[id]/page.tsx` — remove the hardcoded tenant; no new header work needed.
- `ARCHITECTURE_DECISIONS.md` — note under ADR 001: client installs are single-tenant,
  `tenant_id` stays on every table and isolates demo sessions.

**Tests** (`backend/tests/integration/test_tenant_isolation.py`)
- upload as session A → get / file / export / review as session B → 404 each
- no `X-Session-Id` → 400
- list only returns session A's documents

**Watch out.** Existing upload tests send `tenant_id` as a form field — update them.
Old rows keep `demo-tenant-id` and become invisible; that is fine for a demo.

### V1-7 · Measure it — `feat/eval-results-and-metrics` — 2.5-3 h

**Goal.** Real numbers for the README and the resume: per-document timings and token
use, and a reproducible accuracy table per model.

**Files**
- `backend/agents/parser.py` — `extract_text_with_method()` returning
  `(text, "pymupdf" | "pdfplumber" | "ocr" | "image-ocr")`; keep `extract_text()` as a
  thin wrapper so nothing else breaks.
- `backend/agents/extractor.py` — `extract_fields_with_usage()` returning
  `(fields, usage)` from pydantic-ai's `result.usage()`; `extract_fields()` stays as the
  wrapper the evaluation suite already calls.
- `backend/core/metrics.py` — small `timed(name)` context manager collecting
  `{name: seconds}`; no dependency.
- `backend/core/pipeline.py` — collect parse method, per-node seconds and token counts
  into the state; `backend/queue/worker.py` — store them as
  `extraction_results["_metrics"]`.
- `backend/tests/evaluation/run_eval.py` — CLI: run both golden sets against a model,
  write `evals/results/<YYYY-MM-DD>-<model>.json` (per-field hits, per-case accuracy,
  latency, tokens) and print a markdown table. Reuses the matchers in `conftest.py`.
- `README.md` — Evaluation section: the table, model name, date, how to reproduce,
  weakest fields.

**Tests**
- `metrics.timed` records a duration and does not swallow exceptions
- aggregation function turns a list of fake case results into the expected table row
  (pure function, no LLM)
- parser returns the method name that matches the path taken (stub the tiers)

**Cost.** About 20 LLM calls per model run. Run twice: the current
`llama-3.1-8b-instant` and one larger Groq model available that day.

### V1-8 · CI — `chore/github-actions-ci` — 45-60 min

**Files**
- `backend/tests/conftest.py` — set dummy `DATABASE_URL`, `REDIS_URL`,
  `CONFIDENCE_THRESHOLD`, `MAX_UPLOAD_SIZE_MB`, `ENVIRONMENT`,
  `WEBHOOK_TIMEOUT_SECONDS` **only when no `.env` exists at the repo root**, so local
  runs keep using `.env` and CI runs without one.
- `.github/workflows/ci.yml` — two jobs on push and PR:
  - backend: `apt-get install -y tesseract-ocr`, `astral-sh/setup-uv`,
    `uv sync --extra dev`, `uv run ruff check backend`,
    `uv run pytest backend/tests/unit backend/tests/integration -q`
  - frontend: `pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm build` with a dummy
    `NEXT_PUBLIC_API_URL`
- `README.md` — CI badge.

**Watch out.** No secrets in CI, so the evaluation suite must stay out of it. Turn on
branch protection for `main` (PR + green CI) in GitHub settings by hand.

### V1-9 · Deploy — `chore/deploy` — 3 h plus waiting

**Shape.** Vercel (frontend) → Render web service running `backend/Dockerfile` with
`bash backend/start.sh all` (API + ARQ worker in one container, because Render's free
plan has no background workers) → Neon PostgreSQL + Upstash Redis.

**Steps**
1. Neon project, Upstash database, copy both connection strings.
2. Render web service: Docker, `backend/Dockerfile`, health check path `/health`,
   env: `DATABASE_URL`, `REDIS_URL`, `GROQ_API_KEY`, `ENVIRONMENT=production`,
   `ALLOWED_ORIGINS=<vercel url>`, `CONFIDENCE_THRESHOLD=0.75`, `MAX_UPLOAD_SIZE_MB=10`,
   `WEBHOOK_TIMEOUT_SECONDS=10`, `ALLOW_USER_LLM_KEY=false`, `WEBHOOKS_ENABLED=false`.
3. Run `alembic upgrade head` once against Neon (locally with the Neon URL is simplest).
4. Vercel: root `frontend/`, env `NEXT_PUBLIC_API_URL=<render url>`,
   `NEXT_PUBLIC_CONTACT_EMAIL`.
5. Smoke test in the browser: digital PDF → completed; scanned PDF → OCR path;
   invoice with a wrong total → review with `math_mismatch` (after V1-4); approve →
   export JSON and CSV; a second browser cannot see the first browser's documents.

**Watch out.** Free Render web services sleep after 15 minutes, so the first request
can take about a minute — say so in the README and in the Loom. Free Neon databases
expire 30 days after creation, so create it close to the release and keep a seed script.
Check both providers' current free-tier terms on the day.

### V1-10 · README, diagram, Loom — `docs/v1-readme-loom` — 2 h
- [ ] README top: one-line what it does, live link, Loom link, CI badge, architecture
      diagram (Mermaid), eval table, "Design decisions and trade-offs" (queue vs inline,
      deterministic checks vs LLM self-grading, deterministic eval metrics vs
      LLM-as-judge, single container vs separate worker), "Known limitations".
- [ ] Loom (≤3 min): upload scanned invoice → processing → review screen shows reason
      → approve → export. Then 30 s on the eval table.
- [ ] Then run the release checklist above.

**Sprint exit:** live URL + Loom + green CI + eval table. Then stop feature work.

---

## Deferred — until an offer or a paying client asks

- Vendor name normalisation and duplicate-invoice detection
- Audit log (who changed which field, when) + login (NextAuth) for client installs
- Bounding-box highlight on the PDF in the review screen; multi-page table reconstruction
- ERP / Google Sheets / QuickBooks connectors
- Confidence calibration monitoring
- Porting the eval harness to `pydantic_evals` (nice depth signal; only after v1 ships)
- Real multi-tenancy for SaaS (per-tenant rate limits, tenant-scoped keys in DB).
  `tenant_api_keys` table from migration `fbb366fea798` is unused — drop or keep for v2.

---

## Proposed removals — waiting for Pavan's OK (nothing deleted yet)

| What | Where | Why remove | If kept |
|---|---|---|---|
| `BUSINESS_PLAN.md` | local only (untracked, not on GitHub) | "SOC-2 ready", audit logs, $150k roles — claims the code doesn't support | Never `git add` it; move to a private notes folder |
| `ROADMAP.md`, `ARCHITECTURE_AUDIT.md`, `MARKET_ANALYSIS.md` | probably in `git stash@{0}` (3 Sep) | agy/Gemini-era plans with invented numbers | Keep in the stash or a private folder |
| `REVIEW.md`, `BUGS.md`, `CONVERSATION_INSIGHTS.md` | local only, if still present | Old trackers, out of date | Private folder |
| `X-LLM-Key` code path | `api/middleware.py` bypass + unused `SENSITIVE_HEADERS`, `api/routes/documents.py` storage, `core/pipeline.py` Redis read, `queue/worker.py` two `llm_key:` deletes, `ALLOW_USER_LLM_KEY` | Feature is off; less code to explain and secure | Harmless while the setting is `false` |
| `validate_invoice_fields` alias | `agents/validator.py` (bottom) | Not called anywhere; comment says otherwise | Harmless |
| `deepeval` dev dependency | `pyproject.toml`, `requirements.txt` | Not imported anywhere; heavy install; README no longer mentions it | Slower installs and CI |
| `tenant_api_keys` table | migration `fbb366fea798` | Unused | Schema change — decide in v2 |
| `requirements.txt` | repo root | Duplicates `pyproject.toml` + `uv.lock` and drifts | Keep in sync by hand |

---

## Open polish — lower priority

- [ ] `frontend/components/landing/ActionCard.tsx:37-43` uses `next/link` for `mailto:`
      URLs; use `<a>`.
- [ ] Unit/integration tests need a `backend/tests/conftest.py` that sets dummy
      `DATABASE_URL`, `REDIS_URL`, etc., so they run in CI without a `.env` (V1-8).
- [ ] Record webhook delivery results (needs a DB column — schema change, ask first).
- [ ] `validate_webhook_url` runs a blocking DNS lookup inside the upload request.
- [ ] Landing page says "fire a webhook to your system", but the UI has no webhook
      field; it's API-only.
- [ ] `backend/models/db.py:66-69` note about the unused `tenant_api_keys` table.
- [ ] `dispatch_webhook` swallowed errors — covered by V1-5.
- [ ] CSV export writes lists and `_field_confidences` as Python reprs in one cell;
      flatten line items and skip `_`-prefixed keys.
- [ ] `backend/models/db.py` still uses `sqlalchemy.ext.declarative.declarative_base`
      (SQLAlchemy 2.0 `MovedIn20Warning` on every test run); switch to
      `sqlalchemy.orm.declarative_base`. Last remaining project-side warning in pytest.

---

## Past sprints

### Demo cleanup before deploy (closed 11 Sep 2026)

Done:
- [x] Pipeline `_resolve_model` double-read bug fixed; key cleanup moved to `worker.py`.
- [x] Frontend BYOK UI removed; `SettingsModal.tsx` is a read-only usage badge.
- [x] antd v6 `notification` calls use `title:`.
- [x] 429 toast no longer asks users to paste a Groq key.
- [x] "Buy me a coffee" card removed.
- [x] Contact email + Upwork URL moved to `NEXT_PUBLIC_*` env vars.
- [x] README fabricated metrics removed.
- [x] Old `ROADMAP.md` deleted.
- [x] Stale antd-v5 bug entry removed from `REVIEW.md`.
- [x] PR #7 "Phase 1 Foundation" merged 3 Sep (redis pin, math gate, HMAC webhook).
      Merged without tests for the new behaviour; bugs found on review 11 Sep are
      fixed in V1-4 and V1-5.

Carried into Ship v1: run the test suite, browser smoke test, deploy prep, Loom.

---

## How to use this file

- One sprint at a time at the top. When it ships, move it under "Past sprints".
- "Deferred" items move into a sprint only when scope opens — never the other way.
- "Open polish" is for real but non-blocking findings. Promote or defer; don't let
  them rot.
