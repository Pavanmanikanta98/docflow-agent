# Sprint Planner — docflow-agent

Single source of truth for what is in flight, what is deferred, and what is
parked. Update each entry as it lands. Replaces the deleted `ROADMAP.md`,
which was out of sync with `DECISIONS.md`.

---

## Current sprint — Demo cleanup before deploy

**Goal:** Make the public demo defensible to an Upwork client clicking the URL
cold. Strip anything that looks hobbyist, anything fabricated, anything broken.

### Done in this sprint

- [x] Pipeline `_resolve_model` double-read bug — `backend/core/pipeline.py`
      no longer deletes the X-LLM-Key after the first call. Both `extract_node`
      and `validate_node` now use the same key. Cleanup moved to `worker.py`
      (success and failure paths). 1h Redis TTL is the safety net.
- [x] Frontend BYOK UI removed — `lib/api.ts` no longer reads/writes
      `docflow_llm_key`; the `X-LLM-Key` request interceptor is gone.
      `SettingsModal.tsx` is now a read-only usage badge + contact-only modal
      (no key paste, no upsell). Backend still accepts X-LLM-Key as a hidden
      power-user escape hatch.
- [x] Notification API consistency — every `notification.*` call uses
      `title:` (antd v6). The deprecated `message:` prop is no longer used in
      any frontend file.
- [x] 429 toast copy updated — no longer instructs users to paste their own
      Groq key. Now points to "contact for production access".
- [x] "Buy me a coffee" card removed from `app/page.tsx` — wrong audience
      signal for a paid-client portfolio. Section is now 2 cards (custom
      implementation, plugin extension).
- [x] Contact email + Upwork URL moved to `NEXT_PUBLIC_CONTACT_EMAIL` and
      `NEXT_PUBLIC_UPWORK_URL` env vars; `.env.example` updated.
- [x] `README.md` cleaned — fabricated 89% / 85% / ~15% / ~18% / "20+ real
      documents" metrics replaced with eval-suite description; `[link]` and
      `[2-min walkthrough]` placeholders replaced with "coming soon" line.
- [x] `ROADMAP.md` deleted — was out of sync with `DECISIONS.md`.
- [x] Stale antd-v5 `message:` bug entry removed from `REVIEW.md`.

### Remaining in this sprint

- [ ] **Run the test suite** after the backend changes
      (`pytest backend/tests/unit backend/tests/integration -v`) and confirm
      the 6 existing tests still pass.
- [ ] **Smoke-test the full flow in the browser** before declaring done:
      upload PDF → processing → awaiting_review or completed → approve → export.
      Watch the network tab to confirm no `X-LLM-Key` header is ever sent.
- [ ] **Deploy prep**
  - Set `NEXT_PUBLIC_CONTACT_EMAIL`, `NEXT_PUBLIC_UPWORK_URL`,
    `NEXT_PUBLIC_API_URL` in Vercel.
  - Set backend env on Render (Neon `DATABASE_URL`, Upstash `REDIS_URL`,
    `GROQ_API_KEY`, `ENVIRONMENT=production`, `ALLOWED_ORIGINS=<vercel-url>`).
  - Check Render free-tier idle behaviour: ARQ worker must be a separate
    service from the FastAPI web service.
- [ ] **Record the Loom** (3 min, no narration mistakes): upload an invoice →
      show extracted fields → review screen → export JSON. Add link to README.

---

## Deferred to v2 — Real tenancy

These are intentionally out of scope. Document the boundary so future-me does
not start them mid-sprint.

- **Tenant authentication** — magic-link login (NextAuth or Clerk) so each
  user has a stable identity. Replace the hardcoded `tenant_id =
  'demo-tenant-id'` in `DocumentUploader.tsx:31` and `documents/page.tsx:21`
  with the session-derived id.
- **Per-tenant rate limits** — replace the IP-based middleware backstop with
  per-tenant counters once `tenant_id` is real.
- **Tenant-scoped document listing** — currently any caller can see any
  doc list by passing `tenant_id` as a query param. Behind auth, derive
  it server-side and ignore the query param.
- **BYOK key storage in DB** — encrypted at rest, per tenant, not the
  current header passthrough. The `tenant_api_keys` table already exists
  from migration `fbb366fea798` and is currently unused — it can be
  reused or dropped.
- **Audit log** — who reviewed what, when, with what comment. The schema
  already stores `human_review_comments` and `human_review_status`, but
  there is no actor field.

---

## Open polish — Lower priority, do before deploy if time allows

- [ ] `frontend/components/landing/ActionCard.tsx:37-43` uses `<Link>` from
      `next/link` for `mailto:` URLs. `<Link>` is for internal Next.js
      navigation; for `mailto:` and external `https://` URLs an `<a>`
      element is the correct choice. Switch to `<a>`.
- [ ] `backend/api/routes/documents.py:20-21` has a stale comment referencing
      "the api key in header as configured in api.ts" — that header is gone.
      Update the comment.
- [ ] `backend/models/db.py:66-69` notes that the `tenant_api_keys` table is
      no longer used. Either drop it in a new alembic migration or keep the
      note pointing to v2 use.
- [ ] Pipeline BYOK fix has no dedicated test — the existing `test_extractor`
      uses `TestModel` and skips `_resolve_model` entirely. Consider a unit
      test with a mocked Redis client that asserts the key is read but not
      deleted by `_resolve_model`, and that `worker.py` deletes it after
      pipeline completion. Flagged here per RULES.md.

---

## How to use this file

- One sprint at a time at the top. When the current sprint ships, archive
  it under a `## Past sprints` heading at the bottom.
- "Deferred to v2" is the long-lived backlog — items move *out* into the
  current sprint when scope opens, never the other way.
- "Open polish" is for items discovered during a sprint that are real but
  not blockers. Promote to the current sprint or defer to v2 explicitly;
  do not let them rot here.
