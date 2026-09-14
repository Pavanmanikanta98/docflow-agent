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
