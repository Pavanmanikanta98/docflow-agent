"""Routes: POST /{document_id}/review — human approval / rejection."""

from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_db
from backend.models.db import Document, DocumentStatus, HumanReviewStatus
from backend.models.schemas import (
    DocumentReviewRequest,
    DocumentReviewResponse,
)

router = APIRouter(prefix='/documents', tags=['review'])


@router.post("/{document_id}/review", response_model=DocumentReviewResponse)
async def review_document(
    document_id: int,
    review: DocumentReviewRequest,
    db: Session = Depends(get_db),
):
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

    if review.human_review_status == HumanReviewStatus.approved and doc.webhook_url:
        from backend.core.connectors import dispatch_webhook
        await dispatch_webhook({
            "document_id": doc.id,
            "status": doc.status.value,
            "extraction_results": doc.extraction_results,
            "confidence_score": doc.confidence_score,
            "human_review_status": "approved"
        }, url=doc.webhook_url)

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
