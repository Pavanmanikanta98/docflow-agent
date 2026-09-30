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
V1-6 to V1-9 below are written up as implementation sketches, not code yet.

**Audited 18 Sep 2026.** V1-0 to V1-5 are merged (PR #8, #9). Each box below was
checked against the code; ticked boxes carry the evidence, unticked ones say what
is missing. Suite: 57 unit + integration tests pass locally and in CI, ruff clean,
`uv lock --check` clean, `docker build -f backend/Dockerfile .` succeeds.

Checked so far (cloud sandbox, stand-ins where packages were unavailable): parser
routing + PNG OCR tests pass; all 17 webhook unit tests pass; the README signature
snippet verifies against `connectors.sign`.

Decisions taken while implementing (Pavan: adding is OK, deleting is not):
- **V1-3** first gated the `X-LLM-Key` feature behind `ALLOW_USER_LLM_KEY` (any junk
  value in that header had been skipping all rate limits). It has since been removed
  outright — see ADR 003.
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
- [x] `git stash list`; `git stash show --include-untracked --name-only stash@{0}`.
      Recover `ROADMAP.md`, `ARCHITECTURE_AUDIT.md`, `MARKET_ANALYSIS.md` if present.
      *Decided 24 Sep:* all three are in `stash@{0}` and stay there — see "Private notes"
      below. Nothing to recover into the repo.
- [x] Move `BUSINESS_PLAN.md`, `ROADMAP.md`, `ARCHITECTURE_AUDIT.md`,
      `MARKET_ANALYSIS.md` out of the repo (private notes folder). They contain claims
      the code does not support ("SOC-2 ready", audit logs, $150k roles).
      *Decided 24 Sep:* they stay where they are, ignored rather than moved — see
      "Private notes" below. `BUSINESS_PLAN.md` sits at the repo root, untracked, and is
      ignored twice over (`.gitignore` and `.git/info/exclude`); the rest are in the stash.
- [x] README: replace "DeepEval test suite with 20+ cases and accuracy metrics" with
      "deterministic evaluation harness: 20 golden cases (10 invoices, 10 contracts)".
      Remove the `docker-compose up` → frontend/backend claim (compose only runs
      Postgres + Redis). Fix the pydantic-ai line to "3 merged PRs".
      *Evidence:* README has no DeepEval mention; `docker compose up -d  # local
      PostgreSQL + Redis only`; "pydantic-ai contributor (3 merged PRs)". The case count
      moved on with V1-7 — the README now says 32 hand-labelled cases (20 clean, 12
      adversarial), which is what the golden files hold.
- **Done when:** repo root has only code + honest docs; tests still green.

### V1-1 · Make it installable and deployable — `fix/ocr-deps-dockerfile` — 1.5 h
- [x] `backend/agents/parser.py` imports `pytesseract`, but it is not in
      `pyproject.toml` or `requirements.txt` (Pillow only arrives indirectly through
      pdfplumber). A fresh install crashes the worker on import. Declare `pytesseract`
      and `pillow` explicitly (confirm with Pavan first — RULES.md).
      *Evidence:* `pyproject.toml:25-26`, `requirements.txt:28-29`, both in `uv.lock`.
- [x] Add `backend/Dockerfile` (python 3.12 slim + `apt-get install tesseract-ocr`),
      used by both the API and the worker.
      *Evidence:* `backend/Dockerfile` (python:3.12-slim, tesseract-ocr, `uv sync
      --frozen --no-dev`), modes in `backend/start.sh`. Built on 18 Sep; inside the
      image the parser read "INVOICE 4471 TOTAL 715.00" from a generated PNG and from
      an image-only PDF with an empty text layer.
- [x] Unit test: parser returns text for a tiny generated scanned-style PDF (image-only
      page) — skip with a clear reason if the tesseract binary is missing.
      *Evidence:* `test_parser.py::test_scanned_pdf_is_read_with_ocr`, skipped via
      `requires_tesseract` when the binary is missing. It runs (not skips) locally and
      in CI, which installs tesseract.
- **Done when:** `docker build` works and the OCR test passes inside the container.

### V1-2 · Image uploads actually work — `fix/image-upload-parsing` — 45 min
- [x] Upload accepts `image/png` and `image/jpeg`, but the parser always opens bytes
      with `fitz.open(..., filetype="pdf")`, so every image upload fails.
      Pass the MIME type into the pipeline; send images straight to Tesseract.
      *Evidence:* `extract_text(file_bytes, mime_type)` routes images to
      `extract_text_from_image` (`parser.py:91-101`); the worker passes
      `doc.document_mime_type` (`worker.py:38`) into the pipeline (`pipeline.py:54`).
- [x] Tests: PNG bytes → OCR path is used; PDF bytes → PyMuPDF path is used.
      *Evidence:* `test_parser.py::test_images_go_to_ocr_not_the_pdf_path`,
      `test_pdfs_go_to_the_pdf_path`, `test_png_upload_is_read_with_ocr`,
      `test_unsupported_mime_type_is_rejected`.

### V1-3 · Close the hidden BYOK path — `fix/llm-key-header-gate` — 1 h
- [x] Gate `X-LLM-Key` handling (middleware bypass, upload route, `_resolve_model`)
      behind `ALLOW_USER_LLM_KEY=false`. Deleting the code is a proposed removal.
      *Superseded:* removed outright instead of gated (ADR 003, PR #9). No code in
      `backend/` reads the header or the flag; two comments still mention them (see
      Open polish). `test_llm_key_handling.py::test_llm_key_header_does_not_bypass_limits`.
- [x] `backend/core/llm.py` writes the key into `os.environ` on every call, making it
      process-wide (a user key stays there if no server key is set). Build the
      Groq/OpenAI model with an explicit provider object instead — no env mutation.
      *Evidence:* `GroqModel(..., provider=GroqProvider(api_key=key))` and the OpenAI
      equivalent (`llm.py:65`, `llm.py:79`); nothing in `backend/` writes `os.environ`.
- [x] Test: building a model does not change `os.environ`.
      *Evidence:* `test_llm_key_handling.py::test_groq_model_with_explicit_key_does_not_touch_environment`
      and `test_groq_model_with_server_key_does_not_touch_environment`.

### V1-4 · Fix the invoice math gate — `fix/invoice-math-gate` — 2 h
Current bug: `InvoiceFields.line_items` is `list[str]` and there is no `tax_amount`,
so the gate sums 0 and sends almost every invoice with line items to review.
The validator's `status` is also ignored by `route_after_validate`.
- [x] Add optional `subtotal` and `tax_amount` to `InvoiceFields` (keep `line_items`
      as strings — the eval suite depends on that shape).
      *Evidence:* `plugins/invoice.py:22-25`; `line_items` stays `list[str]`
      (`plugins/invoice.py:34`); `test_validator_gate.py::test_invoice_schema_has_subtotal_and_tax`.
- [x] Gate: if `subtotal`, `tax_amount` and `total_amount` are all present and
      `abs(subtotal + tax_amount - total_amount) > 0.01` → force review and record
      the reason. If any is missing → skip the gate (do not punish missing data here).
      *Evidence:* `validator.py::check_arithmetic`, `MATH_TOLERANCE = 0.01`
      (`validator.py:82-114`).
- [x] Record why a document went to review, e.g.
      `extraction_results["_review_reasons"] = ["math_mismatch"]` or
      `["low_confidence:0.62"]`, and show it on the review screen.
      *Evidence:* `low_confidence:` reason built in `pipeline.py:103`, stored as
      `_review_reasons` in `worker.py:60`, shown as "Held for review" with a readable
      sentence in `frontend/app/review/[id]/page.tsx` (`describeReviewReason`).
- [x] Tests (pure function + routing with `TestModel`/`FunctionModel`):
      math OK → gate passes; mismatch → awaiting_review with reason;
      missing subtotal → gate skipped; low confidence → review with reason.
      *Evidence:* `test_validator_gate.py::test_numbers_that_add_up_pass`,
      `test_validate_routing.py::test_math_mismatch_routes_to_review_with_reason`,
      `test_validator_gate.py::test_missing_or_unusable_numbers_skip_the_gate`,
      `test_validate_routing.py::test_low_confidence_routes_to_review_and_says_the_score`.
- [ ] Add `subtotal`/`tax_amount` to golden invoices where the input text has them.
      *Not done:* no golden invoice has either label. Four inputs contain them:
      `inv_001_standard` (subtotal + tax), `inv_003_multiple_items` (subtotal only),
      `inv_004_non_usd_currency` (subtotal + GST), `inv_007_european_format`
      (Zwischensumme + MwSt). Do this before the V1-7 runs, or the eval table will not
      measure the two fields the gate depends on.

### V1-5 · Webhooks: safe and actually idempotent — `fix/webhook-signing-ssrf` — 2 h
- [x] Idempotency key is `uuid4()` per send, so retries look like new events.
      Use `f"doc-{document_id}-{event}"`.
      *Evidence:* `connectors.py::idempotency_key` returns exactly that.
- [x] Sign `f"{timestamp}.{body}"` (so the timestamp can't be replayed with a new body);
      secret from `settings` (no `"dummy_secret"` default); timeout from
      `settings.webhook_timeout_seconds`; log failures instead of `print`.
      *Evidence:* `connectors.py::sign` HMACs `timestamp + b"." + body`; the secret is
      `settings.webhook_secret` and nothing is sent when it is empty; the client uses
      `settings.webhook_timeout_seconds`; failures go to `logger.warning`, no `print`.
- [x] SSRF guard: `webhook_url` comes from a public form. Allow `https` only and reject
      hosts resolving to private, loopback or link-local IPs. Add `WEBHOOKS_ENABLED`
      (default `false` on the public demo).
      *Evidence:* `connectors.py::validate_webhook_url` (https only, every resolved
      address must be `is_global`, IPv4-mapped IPv6 unwrapped), called at upload
      (`routes/documents.py:70`) and again before sending; `webhooks_enabled: bool =
      False` in `config.py`; redirects are not followed.
- [x] Tests: signature verifies with the documented recipe; retry sends the same key;
      `http://127.0.0.1`, `http://169.254.169.254` and `https://10.0.0.5` are rejected.
      *Evidence:* `test_webhooks.py::test_signature_matches_documented_recipe`,
      `test_resending_the_same_event_reuses_the_idempotency_key`,
      `test_rejects_non_public_or_non_https_urls` (http, 127.0.0.1, 169.254.169.254,
      10.0.0.5, a public name resolving to 192.168.x, ::1, ::ffff:127.0.0.1).
- [x] README: a 6-line "verify our webhook signature" snippet.
      *Evidence:* README.md:91-100, the same recipe the signature test checks.

### V1-6 · Demo isolation without login — `fix/demo-session-isolation` — 1.5-2 h

**Done (14 Sep 2026).** 66 unit + integration tests pass, `ruff check backend`
clean. See ADR 004. Two corrections to the sketch below, found while doing it:
`GET /usage` was also taking identity from the caller (a `session_id` query
parameter defaulting to `anonymous`, so anyone could read anyone's quota) and now
uses the same dependency; and the PDF preview could not keep pointing an
`<iframe>` at the file route, because a browser will not put a custom header on an
iframe's own request — it now fetches the bytes with the header and shows a blob
URL. The ownership check lives in one dependency, `get_owned_document`, rather
than being repeated in four route bodies.

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
- `backend/tests/integration/test_usage_count.py`: the usage badge reads the same
  per-session counter the rate limiter increments, and ignores `?session_id=`

**Watch out.** Existing upload tests send `tenant_id` as a form field — update them.
Old rows keep `demo-tenant-id` and become invisible; that is fine for a demo.
The integration fixtures moved to `backend/tests/integration/conftest.py` so the
new module can share them. `backend/tests/conftest.py` (V1-8) only sets the
environment and does not overlap with it.

### V1-7 · Measure it — `feat/eval-results-and-metrics` — 2.5-3 h

**Accuracy half done (18 Sep 2026), metrics half not started.**
Done: the golden set grew to 32 cases (20 clean, 12 adversarial, tagged with
`difficulty` in the golden files); the invoice evaluation now scores `subtotal`
and `tax_amount`; both models were run and the logs plus `SUMMARY.md` are in
`evals/results/`; the README carries the table. Evidence: the five files in
`evals/results/`.

Not done, so the box stays open: `metrics.py`, `extract_text_with_method()`,
`extract_fields_with_usage()`, the pipeline/worker wiring and `run_eval.py`.
No per-case latency or token counts exist, and the results are `.txt` logs plus
a hand-written summary rather than the `<date>-<model>.json` this task asks for.

Two notes from the runs. `llama-3.1-8b-instant` is gone from Groq (404) and the
default is now `openai/gpt-oss-20b` — see ADR 005. The free tier's 8000 TPM
limit produced one 429 over 32 cases, so a full run may need a retry.

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

**Done (15 Sep 2026).** `.github/workflows/ci.yml` runs the backend job (ruff +
57 unit/integration tests, tesseract installed, `uv sync --locked`) and the
frontend job (`pnpm lint`, `pnpm build`) on every push and pull request.
`backend/tests/conftest.py` fills in the six required settings only when the
repo root has no `.env`; verified locally by moving `.env` aside. Two breakages
that would have made CI red on day one were fixed on the same branch — see the
ticked items under "Open polish". Branch protection on `main` still has to be
switched on by hand.

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
   `WEBHOOK_TIMEOUT_SECONDS=10`, `WEBHOOKS_ENABLED=false`.
3. Run `alembic upgrade head` once against Neon (locally with the Neon URL is simplest).
4. Vercel: root `frontend/`, env `NEXT_PUBLIC_API_URL=<render url>`,
   `NEXT_PUBLIC_CONTACT_EMAIL`.
5. Smoke test in the browser: digital PDF → completed; scanned PDF → OCR path;
   invoice with a wrong total → review with `math_mismatch` (after V1-4); approve →
   export JSON and CSV; a second browser cannot see the first browser's documents.
   Any documents uploaded before V1-6 are filed under `demo-tenant-id` and will not
   appear for anyone — expected, not a deploy failure.

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

## Private notes — decided 24 Sep 2026: keep them, never commit them

These are Pavan's own notes and they stay. Nothing is deleted. They are not tracked on
`main`, they are ignored by `.gitignore` (lines 37-43) and also by `.git/info/exclude`
locally, so `git add -A` cannot pick them up even if the tracked ignore file changes.

| What | Where it is now |
|---|---|
| `BUSINESS_PLAN.md` | repo root, untracked and ignored |
| `ROADMAP.md`, `ARCHITECTURE_AUDIT.md`, `MARKET_ANALYSIS.md` | `stash@{0}` (3 Sep) |
| `REVIEW.md`, `BUGS.md`, `CONVERSATION_INSIGHTS.md` | `stash@{0}` (3 Sep) |

Two things follow from that. `stash@{0}` is now the only copy of six of them, so it is not
a stash to drop — move them to a private folder outside the repo when convenient. And the
three local `backup/*` and `chore/test-isolation-and-lint` branches keep `BUSINESS_PLAN.md`
in their git history, which is why they are never pushed; the release checklist's
`git push --tags` would publish any tag that reaches them.

---

## Proposed removals — waiting for Pavan's OK (nothing deleted yet)

| What | Where | Why remove | If kept |
|---|---|---|---|
| `validate_invoice_fields` alias | `agents/validator.py` (bottom) | Not called anywhere; comment says otherwise | Harmless |
| `deepeval` dev dependency | `pyproject.toml`, `requirements.txt` | Not imported anywhere; heavy install; README no longer mentions it | Slower installs and CI |
| `tenant_api_keys` table | migration `fbb366fea798` | Unused | Schema change — decide in v2 |
| `DocumentUploadRequest`, `DocumentListRequest` | `models/schemas.py` | Imported nowhere; both still carry the `tenant_id` field V1-6 removed from the API | Harmless, but they describe a request shape that no longer exists |
| `requirements.txt` | repo root | Duplicates `pyproject.toml` + `uv.lock` and drifts | Keep in sync by hand |

---

## Open polish — lower priority

- [ ] `frontend/components/landing/ActionCard.tsx:37-43` uses `next/link` for `mailto:`
      URLs; use `<a>`.
- [x] Unit/integration tests need a `backend/tests/conftest.py` that sets dummy
      `DATABASE_URL`, `REDIS_URL`, etc., so they run in CI without a `.env` (V1-8).
- [x] `pnpm build` failed on `main` — `frontend/app/page.tsx` used `HandCoins`
      with no import, the leftover "Buy me a coffee" entry from the 11 Sep cleanup.
      Fixed in V1-8 by finishing the removal: entry deleted, heading now "Two ways
      to take this further.", row is `lg:grid-cols-2`.
- [x] `pnpm lint` failed on `main` with 4 errors: three
      `react-hooks/set-state-in-effect` (`AppTour.tsx`, `SettingsModal.tsx`,
      `ThemeRegistry.tsx`) and one `no-explicit-any` (`ExportPanel.tsx`). Fixed in
      V1-8: the "mounted" effects use a shared `lib/useHydrated.ts`
      (`useSyncExternalStore`), the usage poll sets state in the response callback,
      and the export error is narrowed with `instanceof Error`. No rules disabled.
- [ ] `pnpm lint` still prints 2 warnings (not failures):
      `app/review/[id]/page.tsx:87` missing `notification` dependency and
      `components/ExtractionReview.tsx:29` `results` should be wrapped in `useMemo`.
- [ ] Record webhook delivery results (needs a DB column — schema change, ask first).
- [ ] Two comments still describe the removed `X-LLM-Key` / `ALLOW_USER_LLM_KEY` path
      as if it exists: the module docstring of `backend/core/llm.py` and the
      `tenant_api_keys` note in `backend/models/db.py`. ADR 003 removed that path.
- [ ] `validate_webhook_url` checks the resolved address, then httpx resolves the host
      again when it sends, so a DNS answer that changes in between (rebinding) could
      still reach a private address. Fix by connecting to the checked IP. Low priority
      while `WEBHOOKS_ENABLED=false` on the demo.
- [ ] `backend/agents/parser.py` uses `import fitz`; PyMuPDF 1.28 warns that name will
      be removed. Switch to `import pymupdf`.
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
