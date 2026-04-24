"""Pydantic request/response schemas."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from backend.models.db import HumanReviewStatus


class Document(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: str
    document_type: str
    document_url: str
    document_size: int
    document_mime_type: str
    status: str
    extraction_results: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None
    human_review_required: Optional[bool] = None
    human_review_comments: Optional[str] = None
    human_review_status: Optional[str] = None
    human_review_rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class DocumentUploadRequest(BaseModel):
    tenant_id: str = Field(...,description="The tenant ID")
    document_type: str = Field(...,description="The document type")
    webhook_url: Optional[HttpUrl] = Field(None,description="The webhook URL to call when the document is processed")

class DocumentUploadResponse(BaseModel):
    job_id: str = Field(...,description="The job ID")
    status: str = Field(...,description="The status of the document upload")
    message: Optional[str] = Field(None,description="The message from the document upload")
    error: Optional[str] = Field(None,description="The error from the document upload")
    document_type: str = Field(...,description="The document type")
    document_id: str = Field(...,description="The document ID")
    document_url: Optional[str] = Field(None,description="The document URL")
    document_size: int = Field(...,description="The document size")
    document_mime_type: str = Field(...,description="The document MIME type")

class DocumentStatusRequest(BaseModel):
    job_id: str = Field(...,description="The job ID")

class DocumentStatusResponse(BaseModel):
    status: str = Field(...,description="The status of the document upload")
    message: Optional[str] = Field(None,description="The message from the document upload")
    error: Optional[str] = Field(None,description="The error from the document upload")
    document_type: str = Field(...,description="The document type")
    document_id: str = Field(...,description="The document ID")
    document_url: Optional[str] = Field(None,description="The document URL")
    document_size: int = Field(...,description="The document size")
    document_mime_type: str = Field(...,description="The document MIME type")
    extraction_results: Optional[dict] = Field(None,description="The extraction results")
    confidence_score: Optional[float] = Field(None,description="The confidence score")
    human_review_required: Optional[bool] = Field(None,description="Whether human review is required")
    human_review_comments: Optional[str] = Field(None,description="The comments from the human review")
    human_review_status: Optional[str] = Field(None,description="The human review status (approved/rejected)")
    human_review_rejection_reason: Optional[str] = Field(None,description="The reason for the human review rejection")


class DocumentReviewRequest(BaseModel):
    job_id: str = Field(...,description="The job ID")
    review_comments: Optional[str] = Field(None,description="The comments from the review")
    human_review_status: HumanReviewStatus = Field(...,description="The human review status (approved/rejected)")
    human_review_rejection_reason: Optional[str] = Field(None,description="The reason for the human review rejection")

class DocumentReviewResponse(BaseModel):
    status: str = Field(...,description="The status of the document review")
    message: Optional[str] = Field(None,description="The message from the document review")
    error: Optional[str] = Field(None,description="The error from the document review")
    document_type: str = Field(...,description="The document type")
    document_id: str = Field(...,description="The document ID")
    document_url: Optional[str] = Field(None,description="The document URL")
    document_size: int = Field(...,description="The document size")
    document_mime_type: str = Field(...,description="The document MIME type")
    extraction_results: Optional[dict] = Field(None,description="The extraction results")
    confidence_score: float = Field(...,description="The confidence score")

class DocumentExportRequest(BaseModel):
    """An export request only needs the document ID and the desired format."""
    job_id: str = Field(..., description="The document ID to export")
    format: str = Field("json", description="Export format: json or csv")


class DocumentExportResponse(BaseModel):
    status: str = Field(...,description="The status of the document export")
    message: Optional[str] = Field(None,description="The message from the document export")
    error: Optional[str] = Field(None,description="The error from the document export")
    document_type: str = Field(...,description="The document type")
    document_id: str = Field(...,description="The document ID")
    document_url: Optional[str] = Field(None,description="The document URL")
    document_size: int = Field(...,description="The document size")
    document_mime_type: str = Field(...,description="The document MIME type")
    extraction_results: Optional[dict] = Field(None,description="The extraction results")
    confidence_score: float = Field(...,description="The confidence score")

class DocumentDeleteRequest(BaseModel):
    job_id: str = Field(...,description="The job ID")

class DocumentDeleteResponse(BaseModel):
    status: str = Field(...,description="The status of the document delete")
    message: Optional[str] = Field(None,description="The message from the document delete")
    error: Optional[str] = Field(None,description="The error from the document delete")
    document_type: str = Field(...,description="The document type")
    document_id: str = Field(...,description="The document ID")
    document_url: Optional[str] = Field(None,description="The document URL")
    document_size: int = Field(...,description="The document size")
    document_mime_type: str = Field(...,description="The document MIME type")

class DocumentListRequest(BaseModel):
    tenant_id: str = Field(...,description="The tenant ID")
    document_type: Optional[str] = Field(None,description="The document type")
    page: int = Field(1,description="The page number")
    page_size: int = Field(10,description="The page size")

class DocumentListResponse(BaseModel):
    documents: List[Document] = Field(...,description="The list of documents")
    total: int = Field(...,description="The total number of documents")
    page: int = Field(...,description="The page number")
    page_size: int = Field(...,description="The page size")



