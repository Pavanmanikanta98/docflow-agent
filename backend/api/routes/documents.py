"""Routes: POST /upload, GET /status/{job_id}."""

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from sqlalchemy.orm import Session
from redis import Redis
from typing import Optional

from backend.api.deps import get_db, get_redis
from backend.models.db import Document, DocumentStatus
from backend.models.schemas import (
    DocumentUploadResponse, 
    DocumentReviewRequest, 
    DocumentReviewResponse,
    DocumentStatusResponse,
    DocumentListResponse,
    Document as DocumentSchema
)
from backend.queue.jobs import enqueue_process_document

router = APIRouter(prefix='/documents', tags=['documents'])

@router.post('/upload', response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    document_type: str = Form(...),
    webhook_url: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis)
):
    file_bytes = await file.read()
    
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
    tenant_id: str = Query('demo-tenant-id', description="Tenant ID (from query or auth)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(Document).filter(Document.tenant_id == tenant_id)
    total = query.count()
    docs = query.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return DocumentListResponse(
        documents=[DocumentSchema.model_validate(doc) for doc in docs],
        total=total,
        page=page,
        page_size=page_size
    )

@router.get('/{document_id}', response_model=DocumentStatusResponse)
async def get_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
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
        human_review_status=doc.human_review_status.value if doc.human_review_status else None,
        human_review_rejection_reason=doc.human_review_rejection_reason,
    )


@router.post("/{document_id}/review", response_model=DocumentReviewResponse)
async def review_document(
    document_id: int,
    review: DocumentReviewRequest,
    db: Session = Depends(get_db),
):
    from backend.models.db import HumanReviewStatus

    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status not in (DocumentStatus.awaiting_review, DocumentStatus.completed):
        raise HTTPException(
            status_code=400,
            detail=f"Document is not reviewable. Current status: {doc.status.value}"
        )

    doc.human_review_comments = review.review_comments
    doc.human_review_rejection_reason = review.human_review_rejection_reason

    if review.human_review_status == HumanReviewStatus.approved:
        doc.human_review_status = HumanReviewStatus.approved
        doc.status = DocumentStatus.completed
    else:
        doc.human_review_status = HumanReviewStatus.rejected
        doc.status = DocumentStatus.awaiting_review

    db.commit()

    return DocumentReviewResponse(
        status=doc.status.value,
        message=f"Review recorded: {review.human_review_status}",
        document_type=doc.document_type,
        document_id=str(doc.id),
        document_url=doc.document_url,
        document_size=doc.document_size,
        document_mime_type=doc.document_mime_type,
        extraction_results=doc.extraction_results,
        confidence_score=doc.confidence_score,
    )
from fastapi.responses import Response

@router.get('/{document_id}/file')
async def download_document_file(document_id: int, db: Session = Depends(get_db), redis: Redis = Depends(get_redis)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    redis_key = f"doc_bytes:{doc.id}"
    file_bytes = redis.get(redis_key)
    
    if not file_bytes:
        raise HTTPException(status_code=404, detail="File bytes expired or not found in Redis buffer")
        
    return Response(content=file_bytes, media_type=doc.document_mime_type)
