"""ADR 006 — load test: 30 small docs + 1 large doc through the REAL FastAPI
app and the REAL ARQ worker, against `scripts/fake_groq.py` instead of the
real Groq API. Verifies the goal of ADR 006 directly: running out of
capacity makes documents WAIT, never FAIL.

Prerequisite: a local Redis reachable at redis://localhost:6379 (start one
with `docker compose up -d`, or a bare `redis-server`). No Postgres is
needed — this uses an in-memory SQLite database, the same approach the
integration test suite uses, because this test is about the queue/worker/
token-budget layer, not persistence.

Usage:
    uv run python scripts/load_test.py

Writes evals/results/<date>-load-test.json and prints a summary.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "evals" / "results"


def _free_port() -> int:
    """An OS-assigned free port, so a stale fake_groq from a killed previous
    run can never make this run silently talk to the wrong server (a fixed
    port did exactly that once during development — see load-test notes)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


FAKE_GROQ_PORT = _free_port()
TPM = 8000
RPM = 30
NUM_SMALL_DOCS = 30
NUM_SESSIONS = 5
RUN_DEADLINE_SECONDS = 570

# Every setting `backend.core.config.Settings` needs MUST be set before any
# `backend.*` module is imported — the Settings singleton is built at import
# time. A lower completion-token reservation than the production default
# (1024) matches what these tiny fake responses actually use, so the run
# finishes in a few minutes of real time instead of being dominated by an
# oversized reservation on every call.
os.environ.setdefault("GROQ_API_KEY", "fake-groq-key-for-load-test")
os.environ.setdefault("GROQ_BASE_URL", f"http://127.0.0.1:{FAKE_GROQ_PORT}")
os.environ.setdefault("LLM_TPM", str(TPM))
os.environ.setdefault("LLM_RPM", str(RPM))
os.environ.setdefault("LLM_TPD", "200000")
os.environ.setdefault("LLM_RPD", "1000")
os.environ.setdefault("LLM_MAX_COMPLETION_TOKENS", "300")
os.environ.setdefault("SESSION_INFLIGHT_CAP", "5")
os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost/unused")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("CONFIDENCE_THRESHOLD", "0.75")
os.environ.setdefault("MAX_UPLOAD_SIZE_MB", "10")
os.environ.setdefault("ENVIRONMENT", "load-test")
os.environ.setdefault("WEBHOOK_TIMEOUT_SECONDS", "10")
os.environ.setdefault("RATE_LIMIT_PER_SESSION", "1000")
os.environ.setdefault("RATE_LIMIT_PER_IP", "1000")
os.environ.setdefault("RATE_LIMIT_GLOBAL", "10000")

import fitz  # noqa: E402
import httpx  # noqa: E402
import redis as redis_lib  # noqa: E402
from arq.connections import RedisSettings  # noqa: E402
from arq.worker import Worker  # noqa: E402
from sqlalchemy import Enum as SAEnum  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

SMALL_INVOICE_TEMPLATE = """INVOICE
Vendor: Acme Supplies {n}
Invoice Number: INV-{n:04d}
Date: 2026-09-24
Subtotal: 100.00
Tax: 10.00
Total: 110.00
Line Items:
- Widget A - 50.00
- Widget B - 50.00
"""

LARGE_CONTRACT_PARAGRAPH = (
    "This Agreement is entered into between Acme Corp and Example LLC. "
    "The parties agree to the following obligations, terms, and conditions "
    "governing the provision of services, confidentiality, indemnification, "
    "and termination rights under this contract. "
)


def _chunk_text(text: str, size: int = 1800) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _make_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    margin = 40
    for page_text in _chunk_text(text):
        page = doc.new_page()
        rect = fitz.Rect(
            margin, margin, page.rect.width - margin, page.rect.height - margin
        )
        page.insert_textbox(rect, page_text, fontsize=9)
    return doc.tobytes()


async def _wait_for_fake_groq(url: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    async with httpx.AsyncClient() as client:
        while time.time() < deadline:
            try:
                await client.post(url, json={})
                return
            except httpx.HTTPError:
                await asyncio.sleep(0.3)
    raise RuntimeError(f"fake_groq did not become ready at {url}")


def _percentile(data: list[float], pct: float) -> float | None:
    if not data:
        return None
    ordered = sorted(data)
    idx = max(0, min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


async def main() -> None:
    fake_groq = subprocess.Popen(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "fake_groq.py"),
            "--port",
            str(FAKE_GROQ_PORT),
            "--tpm",
            str(TPM),
            "--rpm",
            str(RPM),
        ],
        env=dict(os.environ),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    arq_worker: Worker | None = None
    worker_task: asyncio.Task | None = None
    try:
        await _wait_for_fake_groq(f"http://127.0.0.1:{FAKE_GROQ_PORT}/openai/v1/chat/completions")

        # --- In-memory SQLite DB, wired into both the app and the worker ---
        from backend.models.db import Base

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        for table in Base.metadata.tables.values():
            for col in table.columns:
                if isinstance(col.type, SAEnum):
                    col.type.native_enum = False
                    col.type.create_constraint = False
        Base.metadata.create_all(bind=engine)
        testing_session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=engine
        )

        from backend.core import db as db_module
        from backend.queue import worker as worker_module

        db_module.SessionLocal = testing_session_local
        worker_module.SessionLocal = testing_session_local

        real_redis = redis_lib.from_url(os.environ["REDIS_URL"])
        real_redis.flushdb()
        db_module.redis_client = real_redis
        worker_module.redis_client = real_redis

        from backend.api.deps import get_db, get_redis
        from backend.api.main import app

        def override_get_db():
            session = testing_session_local()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_redis] = lambda: real_redis

        # --- Upload 30 small invoices + 1 large contract via the real ASGI app ---
        documents: list[dict] = []
        transport = httpx.ASGITransport(app=app)
        base_url = "http://loadtest"
        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            for i in range(NUM_SMALL_DOCS):
                pdf_bytes = _make_pdf_bytes(SMALL_INVOICE_TEMPLATE.format(n=i))
                session_id = f"ses_load{i % NUM_SESSIONS:012x}"
                uploaded_at = time.time()
                resp = await client.post(
                    "/api/v1/documents/upload",
                    files={"file": (f"invoice_{i}.pdf", pdf_bytes, "application/pdf")},
                    data={"document_type": "invoice"},
                    headers={"X-Session-Id": session_id},
                )
                resp.raise_for_status()
                documents.append(
                    {
                        "id": int(resp.json()["document_id"]),
                        "kind": "small",
                        "uploaded_at": uploaded_at,
                    }
                )

            # ADR 006 (branch 3): sized well above the 8K TPM ceiling itself
            # (not just the chunking threshold), so this document can only
            # complete via real chunking — a single unsplit request this
            # size would hit RequestTooLargeError outright.
            large_bytes = _make_pdf_bytes(LARGE_CONTRACT_PARAGRAPH * 200)
            uploaded_at = time.time()
            resp = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("contract_large.pdf", large_bytes, "application/pdf")},
                data={"document_type": "contract"},
                headers={"X-Session-Id": "ses_loadlarge0000000"},
            )
            resp.raise_for_status()
            documents.append(
                {
                    "id": int(resp.json()["document_id"]),
                    "kind": "large",
                    "uploaded_at": uploaded_at,
                }
            )

        # --- Run the real ARQ worker in-process until every doc is terminal ---
        from backend.models.db import Document, DocumentStatus
        from backend.queue.worker import process_document, process_document_chunk

        arq_worker = Worker(
            functions=[process_document, process_document_chunk],
            redis_settings=RedisSettings.from_dsn(os.environ["REDIS_URL"]),
            handle_signals=False,
            burst=False,
            poll_delay=0.5,
            # Must match backend.queue.worker.WorkerSettings.max_tries — a low
            # default here would abandon a document mid-capacity-wait and
            # produce a false "timed out" result that is this script's bug,
            # not the pipeline's.
            max_tries=1000,
        )
        worker_task = asyncio.create_task(arq_worker.async_run())

        terminal: dict[int, dict] = {}
        deadline = time.time() + RUN_DEADLINE_SECONDS
        terminal_statuses = {
            DocumentStatus.completed,
            DocumentStatus.awaiting_review,
            DocumentStatus.failed,
        }
        while time.time() < deadline and len(terminal) < len(documents):
            await asyncio.sleep(1.0)
            session = testing_session_local()
            try:
                for d in documents:
                    if d["id"] in terminal:
                        continue
                    row = session.get(Document, d["id"])
                    if row and row.status in terminal_statuses:
                        terminal[d["id"]] = {
                            "status": row.status.value,
                            "finished_at": time.time(),
                        }
            finally:
                session.close()

        capacity_waits_total = int(real_redis.get("metrics:capacity_waits_total") or 0)
        session_inflight_waits_total = int(
            real_redis.get("metrics:session_inflight_waits_total") or 0
        )

        small_wait_seconds: list[float] = []
        failures = 0
        large_completed = False
        timed_out: list[int] = []
        for d in documents:
            info = terminal.get(d["id"])
            if info is None:
                timed_out.append(d["id"])
                continue
            wait = info["finished_at"] - d["uploaded_at"]
            if info["status"] == "failed":
                failures += 1
            if d["kind"] == "small":
                small_wait_seconds.append(wait)
            else:
                large_completed = info["status"] in ("completed", "awaiting_review")

        result = {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "config": {
                "tpm": TPM,
                "rpm": RPM,
                "small_docs": NUM_SMALL_DOCS,
                "large_docs": 1,
                "sessions": NUM_SESSIONS,
                "llm_max_completion_tokens": int(
                    os.environ["LLM_MAX_COMPLETION_TOKENS"]
                ),
                "against": "scripts/fake_groq.py (local, not real Groq)",
            },
            "failures": failures,
            "timed_out_document_ids": timed_out,
            "large_doc_completed": large_completed,
            "capacity_waits_total": capacity_waits_total,
            "session_inflight_waits_total": session_inflight_waits_total,
            "small_doc_wait_seconds": {
                "p50": _percentile(small_wait_seconds, 50),
                "p95": _percentile(small_wait_seconds, 95),
                "min": min(small_wait_seconds) if small_wait_seconds else None,
                "max": max(small_wait_seconds) if small_wait_seconds else None,
                "count": len(small_wait_seconds),
            },
            "pass": failures == 0 and large_completed and not timed_out,
        }

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = RESULTS_DIR / f"{result['date']}-load-test.json"
        out_path.write_text(json.dumps(result, indent=2) + "\n")

        print(json.dumps(result, indent=2))
        print(f"\nWrote {out_path}")
        if not result["pass"]:
            sys.exit(1)

    finally:
        if worker_task is not None:
            worker_task.cancel()
            try:
                await worker_task
            except (asyncio.CancelledError, Exception):
                pass
        if arq_worker is not None:
            try:
                await arq_worker.close()
            except Exception:
                pass
        fake_groq.terminate()
        try:
            fake_groq.wait(timeout=5)
        except subprocess.TimeoutExpired:
            fake_groq.kill()


if __name__ == "__main__":
    asyncio.run(main())
