"""ARQ WorkerSettings — connects to Redis via REDIS_URL from config."""

import logging

from arq import Retry
from arq.connections import RedisSettings
from pydantic_ai.exceptions import ModelHTTPError
from sqlalchemy.orm import Session

from backend.agents.extractor import extract_fields
from backend.agents.parser import extract_pages
from backend.agents.validator import ValidatorOutput, check_arithmetic, validate_fields
from backend.core.chunk_merge import merge_chunk_results
from backend.core.chunk_state import (
    clear_chunk_state,
    get_all_chunk_results,
    get_chunk_text,
    get_total_chunks,
    start_chunked_document,
    store_chunk_result,
)
from backend.core.chunking import should_chunk, split_pages_into_chunks
from backend.core.config import settings
from backend.core.db import SessionLocal, redis_client
from backend.core.llm import llm_client
from backend.core.pipeline import DocFlowState, pipeline, resolve_validation_outcome
from backend.core.token_budget import (
    CapacityWaitError,
    clear_capacity_wait,
    estimate_tokens,
    get_budget_for_model,
    record_capacity_wait,
)
from backend.models.db import Document, DocumentStatus
from backend.plugins import get_plugin

logger = logging.getLogger(__name__)

# A real 429 can still reach us despite our own reservation — our estimate
# and the provider's are computed independently, and under concurrent load
# (several jobs reserving around the same instant) a small drift between
# them is possible even though each reservation is individually correct.
# When the provider's response carries no `retry-after` to size the wait
# from, fall back to a fixed, conservative cooldown rather than guessing.
RATE_LIMIT_FALLBACK_SECONDS = 30.0

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


def _defer_for_capacity(document_id: int, wait_seconds: float) -> None:
    """Record the wait and raise the Retry that defers this job. Never
    returns — every call site treats this as the end of that code path.
    Does not touch either counter: callers increment whichever one (LLM
    capacity vs. session in-flight cap) actually applies."""
    record_capacity_wait(redis_client, document_id, wait_seconds)
    raise Retry(defer=wait_seconds)


def _handle_model_http_error(
    exc: ModelHTTPError, document_id: int, model_name: str
) -> None:
    """A real 429 from the provider, despite our own reservation having
    granted the request. Treat it exactly like CapacityWaitError — defer,
    never fail — rather than letting it become an unhandled exception that
    marks the document failed. Anything other than a 429 is re-raised
    unchanged; this is not a general-purpose error handler.
    """
    if exc.status_code != 429:
        raise exc
    logger.warning(
        "Real 429 for document %s despite our own reservation — treating "
        "as a capacity wait, not a failure.",
        document_id,
    )
    get_budget_for_model(redis_client, model_name).set_cooldown_from_retry_after(
        exc.headers or {}
    )
    redis_client.incr(CAPACITY_WAIT_COUNTER_KEY)
    _defer_for_capacity(document_id, exc.retry_after or RATE_LIMIT_FALLBACK_SECONDS)


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
            _defer_for_capacity(document_id, SESSION_INFLIGHT_RETRY_SECONDS)

        # 1. Mark document as processing
        doc.status = DocumentStatus.processing
        db.commit()

        # 2. pull the bytes from redis
        redis_key = f"doc_bytes:{document_id}"
        file_bytes = redis_client.get(redis_key)
        if not file_bytes:
            raise ValueError(f"No bytes in Redis for key: {redis_key}")

        # 3. Parse once, up front — this is also how we decide whether the
        # document needs chunking (ADR 006). parse_node below is then a
        # no-op: parsing never runs twice.
        pages = extract_pages(file_bytes, doc.document_mime_type)
        full_raw_text = "\n".join(pages)
        if not full_raw_text.strip():
            raise ValueError(
                "No text could be extracted (text layer and OCR both empty)"
            )

        plugin = get_plugin(doc.document_type)
        estimated_tokens = estimate_tokens(
            [
                {"role": "system", "content": plugin.system_prompt},
                {"role": "user", "content": full_raw_text},
            ],
            settings.llm_max_completion_tokens,
        )

        if should_chunk(
            estimated_tokens, settings.llm_tpm, settings.llm_max_request_share
        ):
            budget_tokens = settings.llm_max_request_share * settings.llm_tpm
            chunks = split_pages_into_chunks(
                pages,
                plugin.system_prompt,
                settings.llm_max_completion_tokens,
                budget_tokens,
            )
            start_chunked_document(
                redis_client,
                document_id,
                ["\n".join(chunk_pages) for chunk_pages in chunks],
                full_raw_text,
            )
            from backend.queue.jobs import enqueue_process_document_chunk

            await enqueue_process_document_chunk(document_id, chunk_index=0)
            # The bytes and the raw text now live in the chunk plan; this
            # job's own work (parse, decide, plan, enqueue) is done.
            redis_client.delete(redis_key)
            return

        # 4. Not chunking: run the existing single-request pipeline.
        initial_state: DocFlowState = {
            "document_id": document_id,
            "tenant_id": doc.tenant_id,
            "document_type": doc.document_type,
            "mime_type": doc.document_mime_type,
            "file_bytes": file_bytes,
            "raw_text": full_raw_text,
            "extraction_results": None,
            "confidence_score": None,
            "field_confidences": None,
            "review_reasons": None,
            "human_review_required": None,
            "status": "processing",
            "error": None,
        }
        model_name = getattr(llm_client.get_model(), "model_name", "")
        try:
            result = await pipeline.ainvoke(initial_state)
        except CapacityWaitError as exc:
            logger.info(
                "Deferring document %s: %s", document_id, exc, exc_info=False
            )
            redis_client.incr(CAPACITY_WAIT_COUNTER_KEY)
            _defer_for_capacity(document_id, exc.wait_seconds)
        except ModelHTTPError as exc:
            _handle_model_http_error(exc, document_id, model_name)

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

        await _dispatch_completion_webhook(doc)

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


async def _dispatch_completion_webhook(doc: Document) -> None:
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


async def process_document_chunk(ctx: dict, document_id: int, chunk_index: int) -> None:
    """One chunk of a chunked document (ADR 006).

    Each field is validated against the chunk it came from: extract AND
    validate both run per-chunk here, never against the whole document's
    text. That is not just a literal reading of the spec — a single
    validate_fields call over an entire large document's raw_text would
    itself be exactly the oversized request chunking exists to avoid, so
    finalize below is a pure merge with no LLM call and nothing left that
    can trigger a capacity wait.

    `chunk_index == total_chunks` is the sentinel for "every chunk is in —
    merge and finalize." A capacity wait during a chunk's extract/validate
    call defers via `arq.Retry`; a retry re-enters at the same chunk, since
    nothing before it is redone.
    """

    db: Session = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if not doc:
            return

        total_chunks = get_total_chunks(redis_client, document_id)
        if total_chunks is None:
            # Chunk state expired (or this job is stale) — nothing to do.
            return

        plugin = get_plugin(doc.document_type)
        model = llm_client.get_model()
        model_name = getattr(model, "model_name", "")

        if chunk_index < total_chunks:
            chunk_text = get_chunk_text(redis_client, document_id, chunk_index)
            try:
                fields = await extract_fields(
                    chunk_text, plugin, model=model, redis_client=redis_client
                )
                extracted = fields.model_dump(exclude={"confidence_score"})
                validation = await validate_fields(
                    raw_text=chunk_text,
                    extracted_fields=extracted,
                    model=model,
                    redis_client=redis_client,
                )
            except CapacityWaitError as exc:
                redis_client.incr(CAPACITY_WAIT_COUNTER_KEY)
                _defer_for_capacity(document_id, exc.wait_seconds)
            except ModelHTTPError as exc:
                _handle_model_http_error(exc, document_id, model_name)

            store_chunk_result(
                redis_client,
                document_id,
                chunk_index,
                {
                    "fields": extracted,
                    "field_scores": validation.field_scores,
                    "overall_confidence": validation.overall_confidence,
                },
            )

            from backend.queue.jobs import enqueue_process_document_chunk

            # Always re-enqueue as a new job, even for the sentinel index —
            # this is what puts a big document's next step at the BACK of
            # the shared queue, letting other documents' jobs interleave
            # (round-robin fairness) rather than one document hogging a
            # worker slot for its entire multi-chunk processing time.
            await enqueue_process_document_chunk(document_id, chunk_index + 1)
            return

        # --- chunk_index == total_chunks: merge every chunk. No LLM call. ---
        chunk_data = get_all_chunk_results(redis_client, document_id, total_chunks)
        merge_result = merge_chunk_results(
            plugin, [c.get("fields", {}) for c in chunk_data]
        )

        # A running total can be assembled from different pages ("last"
        # policy); the arithmetic gate only makes sense post-merge.
        math_reasons = check_arithmetic(merge_result.fields)

        # Each kept field's confidence comes from the chunk that field's
        # value came from (its provenance) — never averaged with a chunk
        # whose value was discarded.
        merged_field_scores = {
            field_name: chunk_data[chunk_idx]["field_scores"][field_name]
            for field_name, chunk_idx in merge_result.provenance.items()
            if field_name in chunk_data[chunk_idx].get("field_scores", {})
        }
        contributing_confidences = [
            chunk_data[i].get("overall_confidence", 0.0)
            for i in sorted(set(merge_result.provenance.values()))
        ]
        overall_confidence = (
            sum(contributing_confidences) / len(contributing_confidences)
            if contributing_confidences
            else 0.0
        )
        if math_reasons:
            overall_confidence = 0.0

        validation = ValidatorOutput(
            field_scores=merged_field_scores,
            overall_confidence=overall_confidence,
            status="human_review" if math_reasons else None,
            review_reasons=math_reasons,
        )
        status, reasons = resolve_validation_outcome(
            validation,
            settings.confidence_threshold,
            extra_reasons=merge_result.conflict_reasons,
        )

        clear_capacity_wait(redis_client, document_id)

        extraction_results = dict(merge_result.fields)
        if merged_field_scores:
            extraction_results["_field_confidences"] = merged_field_scores
        if reasons:
            extraction_results["_review_reasons"] = reasons
        if merge_result.provenance:
            extraction_results["_field_provenance"] = merge_result.provenance

        doc.extraction_results = extraction_results
        doc.confidence_score = overall_confidence
        doc.status = DocumentStatus(status)
        db.commit()

        await _dispatch_completion_webhook(doc)

        clear_chunk_state(redis_client, document_id, total_chunks)

    except Retry:
        raise

    except Exception as e:
        db.rollback()
        doc = db.get(Document, document_id)
        if doc:
            doc.status = DocumentStatus.failed
            db.commit()
        raise e

    finally:
        db.close()


class WorkerSettings:
    """ARQ reads this class to configure the worker."""
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [process_document, process_document_chunk]
    # ADR 006: arq's own default (5) would silently ABANDON a document that
    # needs more than 5 capacity-wait retries — arq marks the job permanently
    # failed in its own bookkeeping without ever touching Document.status, so
    # the document would be stuck "processing" forever with no visible error.
    # A capacity wait must be able to survive sustained free-tier congestion
    # (many short defers back to back), so this ceiling is generous; it still
    # bounds a genuinely broken document (e.g. unparsable file) rather than
    # retrying it literally forever.
    max_tries = 1000

