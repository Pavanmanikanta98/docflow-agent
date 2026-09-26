"""ADR 006 — a large document is chunked, processed, and merged end to end.

Drives `backend.queue.worker`'s real functions directly (the same functions
arq calls, just invoked in a loop here instead of through a live arq Worker)
against a real Redis and an in-memory SQLite DB, using pydantic-ai's
FunctionModel — no real LLM calls, no network.
"""

from __future__ import annotations

import pytest
import redis as redis_lib
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import Enum as SAEnum
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import settings
from backend.models.db import Base, Document, DocumentStatus
from backend.queue import worker


def _redis_available() -> bool:
    try:
        client = redis_lib.from_url(
            "redis://localhost:6379/14", socket_connect_timeout=1
        )
        client.ping()
        return True
    except redis_lib.exceptions.RedisError:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(), reason="Redis is not reachable at redis://localhost:6379/14"
)


@pytest.fixture()
def sqlite_session_factory():
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
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield session_local
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def test_redis():
    client = redis_lib.from_url("redis://localhost:6379/14")
    client.flushdb()
    yield client
    client.flushdb()


def _function_model_for_contracts() -> FunctionModel:
    """A FunctionModel that answers both the extractor and validator calls
    for ContractFields, varying its extraction per chunk so the merge is
    exercised meaningfully rather than against identical placeholder data.
    """
    call_count = {"n": 0}

    def respond(messages, info: AgentInfo) -> ModelResponse:
        call_count["n"] += 1
        tool = info.output_tools[0]
        schema = tool.parameters_json_schema

        user_text = ""
        for message in reversed(messages):
            for part in getattr(message, "parts", []):
                if getattr(part, "part_kind", None) == "user-prompt":
                    user_text = str(part.content)
                    break
            if user_text:
                break

        if "field_scores" in schema.get("properties", {}):
            # Validator call — approve everything so this test is about
            # chunking/merging, not the confidence gate.
            args = {"field_scores": {}, "overall_confidence": 0.95}
        else:
            # Extractor call for one chunk.
            page_marker = user_text.strip().splitlines()[0] if user_text.strip() else ""
            args = {
                "parties": ["Acme Corp", "Example LLC"],
                "effective_date": "2026-01-01",
                "expiry_date": None,
                "contract_value": None,
                "currency": "USD",
                "jurisdiction": "Delaware",
                "key_obligations": [f"Obligation noted on: {page_marker}"[:60]],
                "termination_clause": f"Clause seen on: {page_marker}"[:60],
                "confidence_score": 0.9,
            }
        return ModelResponse(
            parts=[ToolCallPart(tool_name=tool.name, args=args)]
        )

    model = FunctionModel(respond)
    model.call_count = call_count  # type: ignore[attr-defined]
    return model


@requires_redis
async def test_forty_page_contract_completes_end_to_end(
    monkeypatch: pytest.MonkeyPatch, sqlite_session_factory, test_redis
) -> None:
    monkeypatch.setattr(worker, "SessionLocal", sqlite_session_factory)
    monkeypatch.setattr(worker, "redis_client", test_redis)
    monkeypatch.setattr(settings, "llm_tpm", 50000)
    monkeypatch.setattr(settings, "llm_rpm", 1000)
    monkeypatch.setattr(settings, "llm_max_request_share", 0.05)
    monkeypatch.setattr(settings, "llm_max_completion_tokens", 20)
    monkeypatch.setattr(settings, "confidence_threshold", 0.75)

    model = _function_model_for_contracts()
    monkeypatch.setattr(worker.llm_client, "get_model", lambda: model)

    pages = [f"Page {i}\n" + ("contract clause text " * 40) for i in range(40)]
    monkeypatch.setattr(worker, "extract_pages", lambda file_bytes, mime: pages)

    enqueued: list[int] = []

    async def fake_enqueue(document_id: int, chunk_index: int) -> None:
        enqueued.append(chunk_index)
        await worker.process_document_chunk({}, document_id, chunk_index)

    monkeypatch.setattr(
        "backend.queue.jobs.enqueue_process_document_chunk", fake_enqueue
    )

    db = sqlite_session_factory()
    doc = Document(
        tenant_id="ses_bigcontract0001",
        document_type="contract",
        document_url="big.pdf",
        document_size=1,
        document_mime_type="application/pdf",
        status=DocumentStatus.pending,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    document_id = doc.id
    test_redis.set(f"doc_bytes:{document_id}", b"irrelevant with extract_pages patched")
    db.close()

    await worker.process_document({}, document_id)

    db = sqlite_session_factory()
    final_doc = db.get(Document, document_id)

    terminal_ok = (DocumentStatus.completed, DocumentStatus.awaiting_review)
    assert final_doc.status in terminal_ok
    assert len(enqueued) > 1, "a 40-page document at this budget must be chunked"

    fields = final_doc.extraction_results
    assert fields["parties"] == ["Acme Corp", "Example LLC"]
    # key_obligations is a "concat" field — one entry per chunk that produced one.
    # -1 for the finalize step, which is not a real chunk.
    assert len(fields["key_obligations"]) == len(enqueued) - 1
    assert "_field_provenance" in fields
    db.close()


@requires_redis
async def test_small_document_finishes_before_a_concurrent_large_documents_last_chunk(
    monkeypatch: pytest.MonkeyPatch, sqlite_session_factory, test_redis
) -> None:
    """Round-robin fairness: enqueuing the big document's next chunk must not
    itself run the chunk — a small document queued behind it gets processed
    first. This test drives the queue explicitly (FIFO) rather than firing
    each chunk recursively, to prove the *order* jobs would run in arq."""
    monkeypatch.setattr(worker, "SessionLocal", sqlite_session_factory)
    monkeypatch.setattr(worker, "redis_client", test_redis)
    monkeypatch.setattr(settings, "llm_tpm", 50000)
    monkeypatch.setattr(settings, "llm_rpm", 1000)
    monkeypatch.setattr(settings, "llm_max_request_share", 0.05)
    monkeypatch.setattr(settings, "llm_max_completion_tokens", 20)
    monkeypatch.setattr(settings, "confidence_threshold", 0.75)

    model = _function_model_for_contracts()
    monkeypatch.setattr(worker.llm_client, "get_model", lambda: model)

    big_pages = [f"Page {i}\n" + ("clause text " * 40) for i in range(20)]
    small_pages = ["A short invoice with one page of text."]

    def fake_extract_pages(file_bytes, mime_type):
        return big_pages if file_bytes == b"big" else small_pages

    monkeypatch.setattr(worker, "extract_pages", fake_extract_pages)

    # A FIFO queue standing in for arq's real queue, so this test controls
    # interleaving explicitly instead of depending on arq/Redis scheduling
    # timing, which would make the test flaky.
    job_queue: list[tuple] = []

    async def fake_enqueue_chunk(document_id: int, chunk_index: int) -> None:
        job_queue.append(("chunk", document_id, chunk_index))

    monkeypatch.setattr(
        "backend.queue.jobs.enqueue_process_document_chunk", fake_enqueue_chunk
    )

    db = sqlite_session_factory()
    big_doc = Document(
        tenant_id="ses_bigdoc00000001",
        document_type="contract",
        document_url="big.pdf",
        document_size=1,
        document_mime_type="application/pdf",
        status=DocumentStatus.pending,
    )
    small_doc = Document(
        tenant_id="ses_smalldoc000001",
        document_type="invoice",
        document_url="small.pdf",
        document_size=1,
        document_mime_type="application/pdf",
        status=DocumentStatus.pending,
    )
    db.add_all([big_doc, small_doc])
    db.commit()
    db.refresh(big_doc)
    db.refresh(small_doc)
    big_id, small_id = big_doc.id, small_doc.id
    test_redis.set(f"doc_bytes:{big_id}", b"big")
    test_redis.set(f"doc_bytes:{small_id}", b"small")
    db.close()

    # Kick off both documents (arq would run these as separate jobs).
    await worker.process_document({}, big_id)
    job_queue.append(("kickoff-small", small_id, None))

    # Drain the queue FIFO — this is what a real arq worker does: jobs run
    # in the order they were enqueued, interleaved across documents.
    finished_order: list[str] = []
    while job_queue:
        kind, doc_id, chunk_index = job_queue.pop(0)
        if kind == "kickoff-small":
            await worker.process_document({}, doc_id)
        else:
            await worker.process_document_chunk({}, doc_id, chunk_index)

        db = sqlite_session_factory()
        small_row = db.get(Document, small_id)
        big_row = db.get(Document, big_id)
        terminal_ok = (DocumentStatus.completed, DocumentStatus.awaiting_review)
        if small_row.status in terminal_ok and "small" not in finished_order:
            finished_order.append("small")
        if big_row.status in terminal_ok and "big" not in finished_order:
            finished_order.append("big")
        db.close()

    assert finished_order[0] == "small", (
        "the small document, queued behind the big document's chunks, "
        f"should finish first — order was {finished_order}"
    )
    assert "big" in finished_order
