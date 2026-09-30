# Architecture Decision Records (ADR)

This document tracks the major architectural and infrastructure decisions made for DocFlow, including the context, options considered, and the final justification.

---

## ADR 001: Deployment & Tenancy Model
**Date:** 2026-09-03  
**Status:** Accepted  

### Context
As we move DocFlow toward production for mid-market SMBs (e.g., logistics, accounting), we must decide how to host the infrastructure and separate client data. Invoices contain highly sensitive PII and financial data.

### Options Considered
1. **Multi-Tenant SaaS:** One massive Postgres database and one backend API serving all clients. Requires complex Row-Level Security (RLS), Auth0 B2B organizations, and strict tenant-ID filtering on every single database query.
2. **Single-Tenant (Managed Hosting):** Deploying a completely isolated instance (Docker container + private DB) for each individual client on AWS or Render.

### Decision
We will proceed with **Single-Tenant (Managed Hosting)**.

### Justification & Business Impact
- **Absolute Data Isolation:** We can guarantee to clients that their financial data is physically separated from their competitors. A code bug cannot accidentally expose Client A's invoices to Client B.
- **Development Velocity:** Bypasses the need to engineer complex Row-Level Security (RLS) in the database, allowing us to ship faster.
- **Premium Pricing Model:** Single-tenant deployments allow us to charge a premium one-time setup fee ($4k-$8k) for "Private Cloud Deployment", aligning with our Go-To-Market strategy.

---

## ADR 002: Authentication Strategy (Human-in-the-Loop)
**Date:** 2026-09-03  
**Status:** Accepted  

### Context
The LangGraph pipeline requires a Human-in-the-Loop (HITL) step when validation fails. We need a way to secure the frontend review screen so unauthorized users cannot approve invoices, and so we can track *who* made edits for the Audit Log.

### Decision
Because we are utilizing a Single-Tenant architecture (ADR 001), we do not need a complex multi-org OAuth setup. We will implement **NextAuth (Auth.js) with simple Credentials/JWT**. 

### Justification
- A single `ADMIN_EMAIL` and `ADMIN_PASSWORD` can be provisioned via `.env` variables for each client's specific deployment.
- It provides a secure HTTP-only session cookie, ensuring the client can refresh their browser without losing access.
- It provides the user's identity to the backend so we can accurately record the `user_id` in the Phase 4 Audit Logs.

---

## ADR 003: The server holds the only LLM key
**Date:** 2026-09-14
**Status:** Accepted (supersedes the caller-supplied key path)

### Context
Two ways of paying the LLM bill were built and then abandoned. First a
`tenant_api_keys` table (migration `fbb366fea798`), meant to hold one key per
tenant; nothing ever read or wrote it. Then a key sent on the upload request in an
`X-LLM-Key` header, cached in Redis against that one document. The second shipped
and, for a while, let any string in that header skip all three rate limits.

### Decision
The server's own key is the only key. `LLMClient.get_model()` still accepts an
explicit provider, key and model — that is what keeps the provider swappable — but
nothing in the request path passes one. The header is read by no code.

### Justification
- A key path that is switched off is still wired into rate limiting, which is
  exactly where a dormant branch does damage when someone switches it on.
- Nobody was using it. The demo runs on the server key and always did.
- A real client wanting their own key needs per-account storage, rotation and
  revocation — none of which the header approach had. It would be rewritten, not
  restored.
- The implementation is in this repo's git history if it is ever wanted; see the
  history of `backend/core/pipeline.py` before v1.0.0.

### Consequence
`tenant_api_keys` stays in the database for now — dropping it needs a migration and
buys nothing at runtime. Revisit in v2.

---

## ADR 004: On the public demo, the browser session is the tenant
**Date:** 2026-09-14
**Status:** Accepted (refines ADR 001 for the demo deployment)

### Context
ADR 001 chose single-tenant deployments for real clients, so `tenant_id` exists on
every table (RULES.md) but never had to separate anybody. The public demo breaks
that assumption: it is one deployment shared by every visitor, it has no login, and
every upload was filed under a `demo-tenant-id` string hardcoded in the frontend.

Three of the six document routes never checked ownership at all — `GET /{id}`,
`/{id}/export` and `POST /{id}/review` looked rows up by primary key alone — and the
two that did check compared against a query parameter the caller supplied. So any
visitor could read, export and approve any other visitor's document by guessing an
integer, and approving somebody else's document also fired their webhook.

### Decision
The browser session id is the tenant id on the demo. It arrives in the `X-Session-Id`
header, which the frontend already attached to every request and the rate limiter
already read. `get_tenant_id` in `backend/api/deps.py` is the only place it is read,
and `get_owned_document` is the only way a route may load a document by id. The
upload form field and the list/file query parameters are gone, so there is no longer
any way for a caller to name a tenant.

### Justification
- The session id already existed and was already being sent. Nothing new to mint.
- One dependency means a route that forgets the check is visible in its signature,
  rather than a missing `if` buried in a handler body.
- Mismatches return 404, not 403, so the response does not confirm that an id exists.
- `tenant_id` keeps doing on the demo what ADR 001 designed it for on client
  installs; nothing about the schema or the single-tenant model changes.

### Consequence
**This is isolation, not authentication.** Anyone who copies another visitor's
session id out of their localStorage gets their documents, and clearing browser
storage abandons the old documents. That is an acceptable trade for a demo with no
accounts; real auth (ADR 002's NextAuth sketch) stays deferred until a client needs it.

Documents uploaded before this change keep `tenant_id = "demo-tenant-id"` and become
invisible, since no browser sends that value as a session id. For a demo whose file
bytes expire after an hour anyway, that is fine.

Two consequences for the browser: a request that arrives without a usable
`X-Session-Id` is refused with 400 rather than being guessed at, and the PDF preview
can no longer point an `<iframe>` straight at the file route, because a browser will
not put a custom header on an iframe's own request. The preview fetches the bytes
with the header and hands the iframe a blob URL instead — which keeps the header as
the single way a caller proves who it is, rather than putting the session id in a URL
where it would leak into history, referrers and access logs.

---

## ADR 005: The default model name follows what Groq actually serves
**Date:** 2026-09-18
**Status:** Accepted (supersedes the model row in DECISIONS.md)

### Context
`DECISIONS.md` picked `llama-3.1-8b-instant` as the default and
`llama-3.3-70b-versatile` as the quality option. On 18 Sep 2026 Groq serves
neither: the first evaluation run returned HTTP 404 `model_not_found` for all
twenty cases, and the account's model list has no Llama chat model at all. The
name was also the default in `config.py`, so a fresh clone without `LLM_MODEL`
set could not extract anything.

### Decision
The default is `openai/gpt-oss-20b`, which the account serves today, and the
larger comparison model is `openai/gpt-oss-120b`. The published evaluation always
names the model and the date it was run, because a hosted model list is not
stable.

### Justification
- A default that 404s turns "clone and run" into a support question.
- Same family for both runs, so the accuracy difference is about size rather than
  vendor.
- Nothing else changes: `LLMClient` already builds the model from a name, so the
  provider stays swappable and no business logic knows the model.

### Consequence
The eval table is only meaningful next to its date. Expect to repeat this when a
hosted model is retired again; the numbers in the README carry the model name and
run date for exactly that reason.

---

## ADR 006: A token budget in front of the LLM, chunking above it, and a cost model on top

**Date:** 2026-09-24
**Status:** Accepted

### Context
The Groq free tier for `gpt-oss` is 30 RPM, 1K RPD, 8K TPM, 200K TPD. Today, any
single request that lands above the TPM limit is rejected with a 429, and the
worker turns that straight into `DocumentStatus.failed` (`backend/queue/worker.py`
re-raises whatever the pipeline raises). A large contract, or an unlucky burst of
small documents, fails a document that would have processed fine a minute later.
There is also no cost visibility: nobody knows what running 1,000 documents a
month would cost on either model, on the free tier or a paid one, until they hit
a bill.

Three problems, one root cause (a fixed, external, non-negotiable capacity
ceiling), so one ADR:

1. **Rate limits should produce backpressure, not failures.**
2. **A single document can exceed a single request's budget.** `gpt-oss-20b`'s
   8K TPM means a multi-page contract's raw text alone can exceed what one
   request is allowed to send.
3. **There is no way to answer "what would this cost at volume?"** without
   guessing at token counts.

### Decision

**Token budget (`backend/core/token_budget.py`).** A Redis-backed token bucket
per model, tracking TPM/RPM/TPD/RPD as four independent counters refilled on
their own clocks. Before every LLM call:
- `estimate_tokens(messages, max_completion_tokens)` (tiktoken, `o200k_base`
  encoding — the closest public encoding to what OSS/GPT-family models use;
  Groq does not publish tokenizer parity, so this is an estimate, not a match)
  produces a request-size estimate that includes the reply budget, not just the
  prompt.
- `reserve(estimated_tokens)` either grants the request or returns
  `wait_seconds`, computed from the bucket that is currently tightest.
- After the call, `settle(reservation, actual_usage)` reconciles the estimate
  against pydantic-ai's `result.usage()`, so the bucket's belief about
  remaining capacity is exact, not just estimated, going forward.
- `sync_from_headers(headers)` reads Groq's `x-ratelimit-remaining-tokens`,
  `x-ratelimit-remaining-requests`, `x-ratelimit-reset-tokens`,
  `x-ratelimit-reset-requests` (confirmed against Groq's rate-limit docs) via
  an httpx event hook on the provider's client, so the bucket tracks Groq's own
  view of capacity, not just our estimate of it.
- A 429 sets a global cooldown key from the response's `retry-after` header;
  every model waits it out together, since a 429 on one request means the
  window is exhausted for all of them.
- Limits are config (`LLM_TPM`, `LLM_RPM`, `LLM_TPD`, `LLM_RPD`, per model),
  defaulting to the free-tier numbers above. Moving to the Developer tier is an
  env change, not a code change.

**The worker never fails a document for lack of capacity.** It calls `reserve`
before each LLM call; on `wait_seconds > 0` it raises ARQ's `Retry(defer=...)`
instead of letting the call happen. A capacity wait is counted separately from
a real error (a new state, `waiting_for_capacity`, distinct from `failed`), and
`GET /documents/{id}` reports it with an estimated start time held in Redis (no
schema change — this is derived, ephemeral state, not a fact about the
document worth persisting). A per-session in-flight cap (new env var) stops one
visitor's batch upload from starving everyone else's single document.

**Chunking (`backend/plugins/base.py`, pipeline, worker) sits above the
budget, not beside it.** When an estimated request exceeds
`LLM_MAX_REQUEST_SHARE` (default 0.5) of TPM, the parsed text is split at page
boundaries into chunks that individually fit. Each chunk is its own ARQ job;
the next chunk of the same document is enqueued only after the previous one
finishes, so a big document does not monopolise the queue — a small document
queued behind it gets its turn in between (round-robin fairness, not FIFO
per-document). Each `DocumentPlugin` declares a merge policy per field —
`first_non_null` for header facts that should appear once, `concat` for
free text that legitimately spans chunks, `last` for a running total that
should reflect the final page — so combining chunk results is a pure,
type-specific function, not pipeline logic that has to know what an invoice
total means. Two chunks disagreeing on a scalar field is not silently
resolved: the merge policy's answer wins, and `chunk_conflict:<field>` is
added as a review reason, so a human sees that the document itself was
inconsistent, not the pipeline. If the day's token budget cannot fit the
document even after chunking, it stays queued with an ETA past the daily
reset — delayed, never failed.

**Cost model (`backend/core/pricing.py`, `scripts/cost_report.py`).** Prices
are config, not a guess: `$/1M` input and output tokens per model, plus the
batch discount, each with the source URL and the date it was checked (prices
move; the check date is what makes a cost figure defensible later). Given
measured token counts from `evals/results/*.json` — never invented — the
report computes cost per document and per 1,000 documents, on-demand and batch,
for both models, and throughput per minute/day on free vs. Developer limits.

**Batch (`scripts/bulk_submit.py`)** targets Groq's Batch API (JSONL,
≤50,000 lines / 200MB, 24h–7d completion window) for the 50% discount at
volume. It needs the paid Developer tier to submit a real batch job, which is
out of scope for this project's free-tier-only budget (see the hard rule in
this session's task). It is built and tested against mocked HTTP only, and the
README says so plainly.

### Alternatives rejected
- **Let 429s fail the document and retry later via a dead-letter queue.**
  Rejected: a document that reaches "failed" reads as a system defect to
  anyone reviewing it, when the actual cause was a shared, expected, and
  temporary capacity ceiling. Distinguishing "waiting" from "broken" in the
  status itself is cheaper than explaining the difference in a support reply.
- **A fixed sleep/backoff instead of a real token bucket.** Rejected: a sleep
  guesses at recovery time; Groq's own `x-ratelimit-*` headers state it
  exactly, and a job that wakes up before the window refills just burns
  another 429.
- **Truncate large documents to fit one request instead of chunking.**
  Rejected outright — silently dropping contract text can hide the very
  obligation or clause the pipeline exists to extract. Chunking costs more
  code; truncation costs correctness.
- **A single merge policy for every field.** Rejected: "first wins" is right
  for a vendor name and wrong for a running total, and "concatenate" is right
  for clause text and wrong for a party list that should de-duplicate, not
  repeat. The plugin is the one place that already knows what each field
  means, so the policy lives there.
- **Silently pick a value on chunk disagreement.** Rejected: a document that
  states two different totals on two pages is a fact about the document a
  reviewer needs, not a pipeline decision to hide.
- **Estimate cost from published benchmark token counts instead of our own
  measurements.** Rejected by this session's "no invented numbers" rule — a
  benchmark's document mix is not this pipeline's document mix.

### Consequences
- A capacity wait is now a first-class, visible state, not an incident. It
  needs its own frontend affordance ("Waiting for capacity — starts ~HH:MM"),
  which is new UI surface.
- Chunking adds real complexity: provenance tracking per field, a merge step,
  and a new failure mode (`chunk_conflict:<field>`) that the review screen has
  to explain in plain English, the same way `math_mismatch` already does.
- The cost model is only as honest as the token counts feeding it. Until a
  metrics-instrumented eval run exists, `cost_report.py` has nothing measured
  to report on, and says so rather than estimating.
- `bulk_submit.py` is unverified against the real Batch API. If Groq changes
  the batch JSONL contract, this would only be caught the first time someone
  with Developer-tier access runs it for real.
- Redis is now load-bearing for correctness (the token bucket), not just for
  the job queue and the file-bytes buffer it already was.

### How we verify
- Unit tests for bucket math (`reserve`/`settle`/refill/day-cap) run against a
  real Redis instance (a `redis` service added to CI), and skip locally with a
  named reason when Redis is unavailable — Lua script behaviour is not
  something a mock should stand in for.
- A worker test with a mocked 429 asserts `Retry(defer=...)` is raised and the
  document status is never set to `failed` for that reason.
- A cooldown test asserts a second reservation attempt during the cooldown
  window is deferred without hitting the (mocked) API again.
- `scripts/fake_groq.py`, a local OpenAI-compatible server enforcing 8K
  TPM / 30 RPM, backs `scripts/load_test.py` (30 small documents + 1 large one,
  through the real API + worker). The pass condition is zero failures and the
  large document completing; results are written to
  `evals/results/<date>-load-test.json` (p50/p95 wait for the small documents,
  completion times) — a second run repeats this with a document above 8K
  tokens once chunking exists, and both files are committed, not just quoted.
- Chunk-splitting, merge policies, and the conflict reason are pure-function
  unit tests. A 40-page synthetic contract is run end-to-end with
  pydantic-ai's `FunctionModel` (no live call) to prove the chunk-then-merge
  path actually completes a document, and an interleaving test proves a small
  document finishes before a concurrent large document's last chunk.
- `cost_report.py`'s numbers are traceable to a specific `evals/results/*.json`
  file by construction — it reads them, it does not invent them.

---

## ADR 007: OCR evaluation — synthetic degradation plus one real scanned set

**Date:** 2026-09-24
**Status:** Accepted

### Context
`backend/agents/parser.py` falls back to Tesseract for scanned PDFs and images,
but nothing measures how much accuracy that fallback costs. "OCR works" (V1-1's
test) is not the same claim as "OCR costs us N points of field accuracy versus a
clean text layer," and only the second is a number worth putting on a resume or
in an interview.

Real-world scans vary along axes a golden set of clean digital PDFs cannot
exercise: DPI, skew, blur, sensor noise, and JPEG compression from a phone
camera. A synthetic set can hold every other variable constant while varying
one degradation at a time — which isolates *why* OCR gets something wrong — but
it cannot prove the pipeline works on an actual photographed or scanned
document, only on a simulation of one.

### Decision
Two complementary sets, not one:

- **Set A (synthetic):** the 20 existing golden invoice/contract texts,
  rendered to images (Pillow) and degraded with fixed random seeds across
  300/200/150 DPI, ±1.5° rotation, Gaussian blur, sensor noise, JPEG quality
  40, and one combined "phone-like" variant. Fixed seeds make every run
  reproducible — the same "scan" is regenerated identically, so a change in
  the number is a change in the pipeline, not a change in the noise.
- **Set B (real):** 50 documents from the CORD-v2 test split (CC BY 4.0,
  `clovaai/cord`), scored only on the fields CORD actually labels (vendor when
  present, subtotal, tax, total, line items). SROIE was considered and
  dropped — its original license could not be verified from this session, and
  an unverifiable license is not a risk worth taking on a portfolio repo that
  claims to be honest about everything else.

`backend/tests/evaluation/run_ocr_eval.py` reports, per variant: CER/WER
(`jiwer`) of Tesseract's raw output against ground truth, and end-to-end field
accuracy (the existing golden-set matchers) for the text-layer baseline versus
each degraded variant. The gap between those two numbers — not the CER/WER
alone — is "the cost of OCR" in the unit that actually matters: fields the
pipeline got right or wrong. Tesseract's version, language data, and PSM mode
are recorded alongside the results, because OCR accuracy is not portable across
Tesseract versions or PSM choices.

A preprocessing experiment (grayscale → Otsu threshold → deskew, versus none)
is run once and decided on the numbers: preprocessing stays in `parser.py`
only if it measurably improves CER/WER or field accuracy on these sets. Either
way, the result — kept or rejected, and why — is recorded in this ADR, not
silently decided in a commit message.

### Alternatives rejected
- **Synthetic degradation only.** Rejected: it proves the pipeline handles a
  simulation of noise, never a real scan or phone photo, which is exactly the
  gap between a benchmark number and an honest one.
- **Real scans only.** Rejected: without controlled single-variable
  degradation, a bad number on a real scan cannot say *which* factor (blur?
  DPI? skew?) caused it — useful for a report, useless for a fix.
- **SROIE for Set B.** Rejected — see Context. A license that cannot be
  verified is treated as unusable, not as probably-fine.
- **Drafting labels for an unlabelled source.** Rejected by this session's
  rules: a field a source does not label is left out of scoring, never
  guessed at from reading the document.
- **Always keep whatever preprocessing looks plausible.** Rejected: "looks
  like it should help" is exactly the kind of unmeasured claim CLAUDE.md's
  hard rules exist to prevent. Preprocessing earns its place in `parser.py` by
  a measured number or it doesn't go in.

### Consequences
- The eval table grows a second dimension (variant, not just model), which
  the README's evaluation section has to present without becoming
  unreadable — a summary row per variant, with the full JSON as the source of
  truth.
- Set B's fields are a subset of `InvoiceFields`. Anything CORD does not label
  (notably `invoice_date`, `invoice_number` unless a second dated-labelled
  source was found within the 20-minute search budget) is only ever measured
  on Set A, and the README states that scope limit next to the numbers rather
  than implying broader coverage.
- A CER regression test on 3 fixed synthetic images runs in CI with no LLM
  call, using a threshold set from the measured baseline plus a stated margin
  — this is a regression guard on Tesseract/preprocessing behavior, not a
  claim about accuracy on unseen documents.
- Tying results to a specific Tesseract version means a Tesseract upgrade
  (e.g. via a base-image bump) should re-run this suite before trusting the
  old numbers still hold.

### How we verify
- `evals/results/<date>-ocr-<model>.json` plus a markdown table, generated by
  `run_ocr_eval.py`, committed alongside the images and labels under
  `evals/datasets/`.
- The CI guard (3 synthetic images, CER only, no network, no LLM) runs on
  every push per the repo's existing "unit + integration only" CI rule.
- The preprocessing decision (kept or rejected) is written into this ADR's
  Decision section once the numbers exist, with the measured delta that
  justified it.

---

## ADR 008: A DeepEval GEval judge for the fields no fuzzy matcher can score

**Date:** 2026-09-24
**Status:** Accepted (reverses the "remove deepeval" line under Proposed
removals in `SPRINT.md`)

### Context
RULES.md and CLAUDE.md rule 7 describe the evaluation harness as fully
deterministic: golden JSON plus fuzzy/number/date matchers. That is the right
tool for `total_amount`, `invoice_date`, `vendor_name` — values with one
correct answer up to formatting. It is the wrong tool for `termination_clause`
and `key_obligations` on a contract (`backend/plugins/contract.py`): free text
that can be correct while using none of the same words as the golden answer.
A fuzzy string match either demands near-verbatim phrasing (and fails
correct rewordings) or is loosened until it stops catching wrong answers —
there is no threshold that does both.

`deepeval` was already a dev dependency, unused, and listed as a candidate for
removal in `SPRINT.md` ("not imported anywhere; heavy install"). This ADR is
the reason to keep it after all, scoped to exactly the fields that need it.

### Decision
DeepEval's `GEval` metric judges only the contract free-text fields
(`termination_clause`, `key_obligations` — confirmed against
`backend/plugins/contract.py`). Every structured field, on every document
type, keeps the deterministic matchers; nothing about `run_eval.py`'s existing
scoring changes for them.

- **The judge is `gpt-oss-120b`**, deliberately a different, larger model than
  whatever extracted the field, wrapped in a `DeepEvalBaseLLM` subclass around
  the existing `LLMClient` (no new LLM-calling code path — the abstraction
  ADR 003 fixed stays the only door to an LLM). Temperature 0, and every
  judge call goes through the ADR 006 token bucket like any other request —
  a judge run is not exempt from the same free-tier ceiling as extraction.
- **`GEval` is configured with explicit `evaluation_steps`**, not a bare
  criteria string, per DeepEval's current documented practice for
  reproducible GEval scoring: compare the candidate against the expected
  output specifically on obligations, conditions, notice periods, and named
  parties; reward faithful rewording; fail a missing or invented material
  condition.
- **The judge is calibrated before it is trusted.** Positive controls (golden
  text, faithfully reworded — must pass) and negative controls (golden text
  with the notice period changed, a party swapped, or an obligation dropped —
  must fail) are run through the same judge. Each judgment runs 3 times; the
  report is the mean and the spread, not a single sample, because an LLM judge
  is not deterministic even at temperature 0.
- **The headline number uses the GEval score only if the controls pass.** If
  the judge fails to separate positive from negative controls, the README
  reports the fuzzy-matcher score instead and says the judge did not
  calibrate — this session does not get to declare a judge trustworthy by
  assertion.
- `evals/judge_calibration.csv` holds real extraction outputs with an empty
  `human_verdict` column for manual spot-checking later; nothing in this
  branch's success depends on that column being filled in.
- `deepeval` moves to its own `eval` extra (pinned version) rather than `dev`
  — it does not run in CI, and pinning means a DeepEval release changing
  GEval's default behavior does not silently change what "the judge passed"
  means between runs.

### Alternatives rejected
- **Extend the fuzzy matcher to free text (e.g. ROUGE/BLEU-style overlap).**
  Rejected: those metrics reward word overlap, not semantic correctness — the
  exact failure mode a judge is meant to fix. A reworded clause that drops the
  notice period can still score well on n-gram overlap.
- **Use the same model as the extractor to judge its own output.** Rejected —
  this is the identical self-grading problem `backend/agents/validator.py`
  was already built to avoid for structured fields (its docstring says so
  explicitly); a judge should not share the extractor's blind spots.
- **Trust the judge without calibration controls.** Rejected: an uncalibrated
  LLM-as-judge score is exactly the kind of confident-but-unverified number
  CLAUDE.md's "no invented numbers" rule is written against, even though a
  judge score is not literally invented — it is unverified, which is the same
  problem from a different direction.
- **Score every field type with GEval, not just contract free text.**
  Rejected — the deterministic matchers already answer the structured-field
  question exactly and cheaply; a judge call costs tokens and free-tier
  capacity for no better an answer.
- **Run each judgment once.** Rejected: temperature 0 reduces but does not
  eliminate run-to-run variance in LLM judges; reporting a single sample as
  "the" score overstates precision that was not measured.

### Consequences
- CLAUDE.md rule 7 changes from "does not use DeepEval" to naming DeepEval's
  scoped role — the rule now has to stay accurate as the judge's scope
  changes, rather than being a blanket statement.
- The evaluation report grows a second axis for contract free-text fields
  (fuzzy score and GEval score side by side), which needs explaining in
  `docs/deepeval.md` so the numbers are defensible in an interview, not just
  in a JSON file.
- A DeepEval judge run costs real LLM calls (extraction + judge, 3x for each
  case for the mean/spread) against the same free-tier budget as everything
  else — it is not free to re-run casually.
- If DeepEval's GEval implementation changes its scoring behavior in a future
  release, the pinned version in the `eval` extra is what keeps a historical
  `evals/results/<date>-judge-*.json` file interpretable; upgrading the pin
  is a deliberate act, not a side effect of `uv sync`.

### How we verify
- Calibration controls (positive/negative, 3 runs each) are the acceptance
  gate for trusting GEval's headline number at all; their pass/fail and
  the mean/spread are reported plainly, not hidden inside an aggregate.
- `evals/results/<date>-judge-<model>.json` holds the fuzzy score and the
  GEval score side by side for the scoped fields, naming the model and date.
- `evals/judge_calibration.csv` is committed for manual review; it is not a
  precondition for anything else in this ADR.
- `docs/deepeval.md` documents what GEval does, why the judge is a different
  model, how the controls calibrate it, how to run it, and how to read the
  scores — written for an interview, not for a DeepEval contributor.
- `deepeval` is never installed by `uv sync --extra dev`, so CI's dependency
  set and runtime are unaffected by this ADR.
