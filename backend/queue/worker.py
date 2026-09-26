"""ARQ WorkerSettings — connects to Redis via REDIS_URL from config."""

import logging

from arq import Retry
from arq.connections import RedisSettings
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.db import SessionLocal, redis_client
from backend.core.pipeline import DocFlowState, pipeline
from backend.core.token_budget import (
    CapacityWaitError,
    clear_capacity_wait,
    record_capacity_wait,
)
from backend.models.db import Document, DocumentStatus

logger = logging.getLogger(__name__)

# Short retry for the per-session in-flight cap — this is queue fairness
# between sessions, not a real capacity ceiling, so the wait is small and
# fixed rather than computed from a rate-limit window.
SESSION_INFLIGHT_RETRY_SECONDS = 5

# Simple counters, not persisted per-document: how many times a job was
# deferred for lack of LLM capacity vs. the per-session in-flight cap, kept
# separate from real failures so a healthy-but-busy free tier does not look
# like a broken pipeline.
CAPACITY_WAIT_COUNTER_KEY = "metrics:capacity_waits_total"
SESSION_INFLIGHT_WAIT_COUNTER_KEY = "metrics:session_inflight_waits_total"


async def process_document(ctx: dict, document_id: int) -> None:
    """
    Main ARQ task. Called by the worker when a job is dequeued.
    Reads bytes from Redis, extracts fields, updates the DB.

    Two ways this defers instead of failing (ADR 006):
      - the per-session in-flight cap is already full — another document
        for the same session is still processing.
      - the LLM token budget has no room right now (CapacityWaitError from
        the extractor/validator agents).
    Both raise `arq.Retry`, which arq re-queues after `defer` seconds. A
    capacity wait is never written to `Document.status` — that stays
    whatever it already was, and the wait itself is tracked in Redis only
    (see `backend.core.token_budget`), so `GET /documents/{id}` can report
    it without a DB schema change.
    """

    db: Session = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if not doc:
            return

        # Per-session in-flight cap: check before mutating anything, so a
        # deferred job leaves the document exactly as it was.
        in_flight = (
            db.query(Document)
            .filter(
                Document.tenant_id == doc.tenant_id,
                Document.status == DocumentStatus.processing,
                Document.id != doc.id,
            )
            .count()
        )
        if in_flight >= settings.session_inflight_cap:
            redis_client.incr(SESSION_INFLIGHT_WAIT_COUNTER_KEY)
            record_capacity_wait(
                redis_client, document_id, SESSION_INFLIGHT_RETRY_SECONDS
            )
            raise Retry(defer=SESSION_INFLIGHT_RETRY_SECONDS)

        # 1. Mark document as processing
        doc.status = DocumentStatus.processing
        db.commit()

        # 2. pull the bytes from redis
        redis_key = f"doc_bytes:{document_id}"
        file_bytes = redis_client.get(redis_key)
        if not file_bytes:
            raise ValueError(f"No bytes in Redis for key: {redis_key}")

        # 3 & 4. Run the full LangGraph pipeline: parse → extract → route
        initial_state: DocFlowState = {
            "document_id": document_id,
            "tenant_id": doc.tenant_id,
            "document_type": doc.document_type,
            "mime_type": doc.document_mime_type,
            "file_bytes": file_bytes,
            "raw_text": "",
            "extraction_results": None,
            "confidence_score": None,
            "field_confidences": None,
            "review_reasons": None,
            "human_review_required": None,
            "status": "processing",
            "error": None,
        }
        try:
            result = await pipeline.ainvoke(initial_state)
        except CapacityWaitError as exc:
            logger.info(
                "Deferring document %s: %s", document_id, exc, exc_info=False
            )
            redis_client.incr(CAPACITY_WAIT_COUNTER_KEY)
            record_capacity_wait(redis_client, document_id, exc.wait_seconds)
            raise Retry(defer=exc.wait_seconds) from exc

        clear_capacity_wait(redis_client, document_id)

        # 5. Write pipeline output back to DB
        if result["status"] == "failed":
            raise ValueError(result.get("error") or "Pipeline failed")

        # Embed per-field confidences into extraction_results (no new DB column needed)
        extraction_results = result["extraction_results"] or {}
        if result.get("field_confidences"):
            extraction_results["_field_confidences"] = result["field_confidences"]
        if result.get("review_reasons"):
            extraction_results["_review_reasons"] = result["review_reasons"]

        doc.extraction_results = extraction_results
        doc.confidence_score = result["confidence_score"]
        doc.status = DocumentStatus(result["status"])

        db.commit()

        if doc.webhook_url and doc.status == DocumentStatus.completed:
            from backend.core.connectors import dispatch_webhook
            await dispatch_webhook(
                document_id=doc.id,
                event="document.completed",
                payload={
                    "document_id": doc.id,
                    "status": doc.status.value,
                    "extraction_results": doc.extraction_results,
                    "confidence_score": doc.confidence_score,
                },
                url=doc.webhook_url,
            )


        # 6. clean up Redis - the uploaded bytes are no longer needed
        redis_client.delete(redis_key)

    except Retry:
        # A capacity wait is not a failure — never fall through to the
        # generic handler below, which would mark the document failed.
        raise

    except Exception as e:

        db.rollback()
        doc = db.get(Document , document_id)

        if doc:
            # Mark as failed and log error
            doc.status = DocumentStatus.failed
            db.commit()
        raise e

    finally:
        db.close()



class WorkerSettings:
    """ARQ reads this class to configure the worker."""
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [process_document]
    # ADR 006: arq's own default (5) would silently ABANDON a document that
    # needs more than 5 capacity-wait retries — arq marks the job permanently
    # failed in its own bookkeeping without ever touching Document.status, so
    # the document would be stuck "processing" forever with no visible error.
    # A capacity wait must be able to survive sustained free-tier congestion
    # (many short defers back to back), so this ceiling is generous; it still
    # bounds a genuinely broken document (e.g. unparsable file) rather than
    # retrying it literally forever.
    max_tries = 1000

