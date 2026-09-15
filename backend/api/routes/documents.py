"""Routes: upload, list, status, download."""
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import Response
from redis import Redis
from sqlalchemy.orm import Session

from backend.api.deps import (
    get_db,
    get_owned_document,
    get_redis,
    get_tenant_id,
)
from backend.core.config import settings
from backend.core.connectors import WebhookURLRejectedError, validate_webhook_url
from backend.models.db import Document, DocumentStatus
from backend.models.schemas import Document as DocumentSchema
from backend.models.schemas import (
    DocumentListResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from backend.queue.jobs import enqueue_process_document

ALLOWED_MIMES = {"application/pdf", "image/png", "image/jpeg"}

router = APIRouter(prefix='/documents', tags=['documents'])

@router.post('/upload', response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    webhook_url: Optional[str] = Form(None),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis)
):
    # --- Validate file MIME type ---
    if file.content_type not in ALLOWED_MIMES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported file type: {file.content_type}. "
                "Only PDF and image files are accepted."
            ),
        )

    # --- Validate document type against known plugins ---
    if document_type not in ("invoice", "contract"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported document type: {document_type}. "
                "Supported: invoice, contract."
            ),
        )

    # --- Webhook URL: only when webhooks are enabled, and only public https hosts ---
    if webhook_url:
        if not settings.webhooks_enabled:
            raise HTTPException(
                status_code=422,
                detail="Webhooks are disabled on this deployment.",
            )
        try:
            validate_webhook_url(webhook_url)
        except WebhookURLRejectedError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    file_bytes = await file.read()

    # --- Enforce upload size limit ---
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large ({len(file_bytes) / (1024*1024):.1f}MB). "
                f"Maximum: {settings.max_upload_size_mb}MB."
            ),
        )

    new_doc = Document(
        tenant_id=tenant_id,
        document_type=document_type,
        document_url=file.filename,
        document_size=len(file_bytes),
        document_mime_type=file.content_type,
        webhook_url=webhook_url,
        status=DocumentStatus.pending
    )

    try:
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    redis_key = f"doc_bytes:{new_doc.id}"
    redis.setex(redis_key, 3600, file_bytes)

    await enqueue_process_document(new_doc.id)

    return DocumentUploadResponse(
        job_id=str(new_doc.id),
        status=new_doc.status.value,
        message="Document uploaded securely to temporary buffer pending extraction.",
        document_type=new_doc.document_type,
        document_id=str(new_doc.id),
        document_url=new_doc.document_url,
        document_size=new_doc.document_size,
        document_mime_type=new_doc.document_mime_type,
    )


@router.get('', response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    query = db.query(Document).filter(Document.tenant_id == tenant_id)
    total = query.count()
    docs = (
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return DocumentListResponse(
        documents=[DocumentSchema.model_validate(doc) for doc in docs],
        total=total,
        page=page,
        page_size=page_size
    )

@router.get('/{document_id}', response_model=DocumentStatusResponse)
async def get_document(
    doc: Document = Depends(get_owned_document),
):
    return DocumentStatusResponse(
        status=doc.status.value,
        message="Document status retrieved",
        document_type=doc.document_type,
        document_id=str(doc.id),
        document_url=doc.document_url,
        document_size=doc.document_size,
        document_mime_type=doc.document_mime_type,
        extraction_results=doc.extraction_results,
        confidence_score=doc.confidence_score,
        human_review_required=doc.human_review_required,
        human_review_comments=doc.human_review_comments,
        human_review_status=(
            doc.human_review_status.value if doc.human_review_status else None
        ),
        human_review_rejection_reason=doc.human_review_rejection_reason,
    )


@router.get('/{document_id}/file')
async def download_document_file(
    doc: Document = Depends(get_owned_document),
    redis: Redis = Depends(get_redis),
):
    redis_key = f"doc_bytes:{doc.id}"
    file_bytes = redis.get(redis_key)

    if not file_bytes:
        raise HTTPException(
            status_code=404, detail="File bytes expired or not found in Redis buffer"
        )

    return Response(content=file_bytes, media_type=doc.document_mime_type)
