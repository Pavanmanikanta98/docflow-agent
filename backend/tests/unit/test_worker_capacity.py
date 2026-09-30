"""ADR 006 — the worker defers instead of failing when capacity runs out.

Both the per-session in-flight cap and a real LLM capacity wait (mocked 429,
surfaced as `CapacityWaitError`) must raise `arq.Retry` and leave the
document's DB status untouched — never `failed`.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from arq import Retry
from pydantic_ai.exceptions import ModelHTTPError

from backend.core.token_budget import CapacityWaitError
from backend.models.db import DocumentStatus
from backend.queue import worker


def _fake_document(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1,
        tenant_id="ses_aaaaaaaaaaaaaaaa",
        document_type="invoice",
        document_mime_type="application/pdf",
        webhook_url=None,
        status=DocumentStatus.pending,
        extraction_results=None,
        confidence_score=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _FakeQuery:
    """Stands in for db.query(Document).filter(...).count()."""

    def __init__(self, count: int):
        self._count = count

    def filter(self, *args, **kwargs):
        return self

    def count(self):
        return self._count


def _fake_db(doc, in_flight_count=0):
    db = MagicMock()
    db.get.return_value = doc
    db.query.return_value = _FakeQuery(in_flight_count)
    return db


@pytest.fixture()
def patched_redis(monkeypatch):
    fake_redis = MagicMock()
    fake_redis.get.return_value = b"%PDF-1.4 fake bytes"
    monkeypatch.setattr(worker, "redis_client", fake_redis)
    # The worker now parses eagerly (to decide chunking) before it ever
    # reaches pipeline.ainvoke; these tests are about dispatch logic, not
    # real PDF parsing, so a small canned page stands in for it.
    monkeypatch.setattr(worker, "extract_pages", lambda *a, **k: ["INVOICE small text"])
    return fake_redis


async def test_capacity_wait_error_defers_instead_of_failing(
    monkeypatch: pytest.MonkeyPatch, patched_redis
) -> None:
    doc = _fake_document()
    db = _fake_db(doc)
    monkeypatch.setattr(worker, "SessionLocal", lambda: db)

    async def fake_ainvoke(state):
        raise CapacityWaitError(wait_seconds=12.5, model="openai/gpt-oss-20b")

    monkeypatch.setattr(worker.pipeline, "ainvoke", fake_ainvoke)

    with pytest.raises(Retry) as exc_info:
        await worker.process_document({}, doc.id)

    assert exc_info.value.defer_score == pytest.approx(12500, abs=50)
    # Never set to failed for a capacity wait.
    assert doc.status != DocumentStatus.failed
    db.rollback.assert_not_called()


async def test_capacity_wait_records_estimated_start_in_redis(
    monkeypatch: pytest.MonkeyPatch, patched_redis
) -> None:
    doc = _fake_document()
    db = _fake_db(doc)
    monkeypatch.setattr(worker, "SessionLocal", lambda: db)

    async def fake_ainvoke(state):
        raise CapacityWaitError(wait_seconds=30, model="openai/gpt-oss-20b")

    monkeypatch.setattr(worker.pipeline, "ainvoke", fake_ainvoke)

    with pytest.raises(Retry):
        await worker.process_document({}, doc.id)

    # record_capacity_wait writes a "capacity_wait:doc:<id>" key via redis.set
    written_keys = [call.args[0] for call in patched_redis.set.call_args_list]
    assert any(key == f"capacity_wait:doc:{doc.id}" for key in written_keys)


async def test_real_429_defers_instead_of_failing(
    monkeypatch: pytest.MonkeyPatch, patched_redis
) -> None:
    """A genuine 429 from the provider can still slip through despite our
    own reservation (our estimate and the provider's are independent, and
    can drift apart under concurrent load) — this must defer exactly like
    CapacityWaitError, not crash the job as an unhandled exception."""
    doc = _fake_document()
    db = _fake_db(doc)
    monkeypatch.setattr(worker, "SessionLocal", lambda: db)

    async def fake_ainvoke(state):
        raise ModelHTTPError(
            status_code=429,
            model_name="openai/gpt-oss-20b",
            body={"error": {"message": "Rate limit reached for this model."}},
            headers={"retry-after": "8"},
        )

    monkeypatch.setattr(worker.pipeline, "ainvoke", fake_ainvoke)

    with pytest.raises(Retry) as exc_info:
        await worker.process_document({}, doc.id)

    assert exc_info.value.defer_score == pytest.approx(8000, abs=50)
    assert doc.status != DocumentStatus.failed
    db.rollback.assert_not_called()


async def test_non_429_model_http_error_still_fails(
    monkeypatch: pytest.MonkeyPatch, patched_redis
) -> None:
    """A non-429 provider error (e.g. 500) is a real failure, not a capacity
    wait — only 429 gets the defer treatment."""
    doc = _fake_document()
    db = _fake_db(doc)
    monkeypatch.setattr(worker, "SessionLocal", lambda: db)

    async def fake_ainvoke(state):
        raise ModelHTTPError(
            status_code=500, model_name="openai/gpt-oss-20b", body="internal error"
        )

    monkeypatch.setattr(worker.pipeline, "ainvoke", fake_ainvoke)

    with pytest.raises(ModelHTTPError):
        await worker.process_document({}, doc.id)

    assert doc.status == DocumentStatus.failed


async def test_real_error_still_marks_document_failed(
    monkeypatch: pytest.MonkeyPatch, patched_redis
) -> None:
    """A genuine failure (not a capacity wait) keeps its old behaviour."""
    doc = _fake_document()
    db = _fake_db(doc)
    monkeypatch.setattr(worker, "SessionLocal", lambda: db)

    async def fake_ainvoke(state):
        raise ValueError("boom")

    monkeypatch.setattr(worker.pipeline, "ainvoke", fake_ainvoke)

    with pytest.raises(ValueError):
        await worker.process_document({}, doc.id)

    assert doc.status == DocumentStatus.failed
    db.rollback.assert_called_once()


async def test_session_inflight_cap_defers_before_touching_status(
    monkeypatch: pytest.MonkeyPatch, patched_redis
) -> None:
    from backend.core.config import settings

    monkeypatch.setattr(settings, "session_inflight_cap", 1)
    doc = _fake_document(status=DocumentStatus.pending)
    # Simulate 1 other document of this tenant already processing.
    db = _fake_db(doc, in_flight_count=1)
    monkeypatch.setattr(worker, "SessionLocal", lambda: db)

    with pytest.raises(Retry) as exc_info:
        await worker.process_document({}, doc.id)

    assert exc_info.value.defer_score == worker.SESSION_INFLIGHT_RETRY_SECONDS * 1000
    # Status was never flipped to processing — the job never actually started.
    assert doc.status == DocumentStatus.pending
    db.commit.assert_not_called()


def test_worker_settings_raises_max_tries_above_arq_default() -> None:
    """arq's own default (5) would abandon a document mid-capacity-wait —
    arq marks the job permanently failed in its own bookkeeping without
    ever touching Document.status, leaving it stuck "processing" forever
    with no visible error. This is exactly the failure scripts/load_test.py
    hit live: jobs abandoned with "max retries 5 exceeded" well before the
    free-tier TPM/RPM congestion actually cleared."""
    assert worker.WorkerSettings.max_tries > 5


async def test_session_inflight_cap_allows_when_under_cap(
    monkeypatch: pytest.MonkeyPatch, patched_redis
) -> None:
    from backend.core.config import settings

    monkeypatch.setattr(settings, "session_inflight_cap", 2)
    doc = _fake_document(status=DocumentStatus.pending)
    db = _fake_db(doc, in_flight_count=1)  # 1 < cap of 2
    monkeypatch.setattr(worker, "SessionLocal", lambda: db)

    async def fake_ainvoke(state):
        return {
            "status": "completed",
            "extraction_results": {"total_amount": 1.0},
            "confidence_score": 0.9,
            "field_confidences": {},
            "review_reasons": [],
        }

    monkeypatch.setattr(worker.pipeline, "ainvoke", fake_ainvoke)

    await worker.process_document({}, doc.id)

    assert doc.status == DocumentStatus.completed
