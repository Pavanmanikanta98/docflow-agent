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
