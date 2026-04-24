"""ARQ WorkerSettings — connects to Redis via REDIS_URL from config."""

from sqlalchemy.orm import Session
from arq.connections import RedisSettings

from backend.core.config import settings
from backend.core.db import SessionLocal, redis_client
from backend.models.db import Document, DocumentStatus
from backend.core.pipeline import pipeline, DocFlowState


async def process_document(ctx: dict, document_id: int) -> None:
    """
    Main ARQ task. Called by the worker when a job is dequeued.
    Reads bytes from Redis, extracts fields, updates the DB.
    """

    db: Session = SessionLocal()
    try:
        # 1. Mark documnet as processing
        doc = db.get(Document, document_id)
        if not doc:
            return
        doc.status = DocumentStatus.processing
        db.commit()

        # 2. pull the bytes from redis
        redis_key =  f"doc_bytes:{document_id}"
        file_bytes = redis_client.get(redis_key)
        if not file_bytes:
            raise ValueError(f"No bytes in Redis for key: {redis_key}")

        # 3 & 4. Run the full LangGraph pipeline: parse → extract → route
        initial_state: DocFlowState = {
            "document_id": document_id,
            "document_type": doc.document_type,
            "file_bytes": file_bytes,
            "raw_text": "",
            "extraction_results": None,
            "confidence_score": None,
            "field_confidences": None,
            "status": "processing",
            "error": None,
        }
        result = await pipeline.ainvoke(initial_state)

        # 5. Write pipeline output back to DB
        if result["status"] == "failed":
            raise ValueError(result.get("error") or "Pipeline failed")

        # Embed per-field confidences into extraction_results (no new DB column needed)
        extraction_results = result["extraction_results"] or {}
        if result.get("field_confidences"):
            extraction_results["_field_confidences"] = result["field_confidences"]

        doc.extraction_results = extraction_results
        doc.confidence_score = result["confidence_score"]
        doc.status = DocumentStatus(result["status"])

        db.commit()

        if doc.webhook_url and doc.status == DocumentStatus.completed:
            import httpx
            try:
                async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
                    await client.post(doc.webhook_url, json={
                        "document_id": doc.id,
                        "status": doc.status.value,
                        "extraction_results": doc.extraction_results,
                        "confidence_score": doc.confidence_score,
                    }
                    )
            except Exception:
                pass
                    

        # 6. clean up Redis - bytes no longer needed
        redis_client.delete(redis_key)

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
    
