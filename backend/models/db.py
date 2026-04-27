"""SQLAlchemy models. Every table must include tenant_id."""

import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, JSON, DateTime, Boolean, Float, Enum
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class DocumentStatus(str, enum.Enum):
    """Lifecycle states for a document."""
    pending = "pending"           # uploaded, nothing started yet
    processing = "processing"     # extraction pipeline is running
    awaiting_review = "awaiting_review"  # extraction done, needs human eye
    completed = "completed"       # fully processed and approved
    failed = "failed"             # extraction or processing error


class HumanReviewStatus(str, enum.Enum):
    """Outcome of a human review."""
    approved = "approved"
    rejected = "rejected"


class Document(Base):
    __tablename__ = "documents"

    # --- Core identity (always available at upload time) ---
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    document_type = Column(String, nullable=False)
    document_url = Column(String, nullable=False)
    document_size = Column(Integer, nullable=False)
    document_mime_type = Column(String, nullable=False)
    webhook_url = Column(String, nullable=True) 

    # Tracks where the document is in its lifecycle
    status = Column(
        Enum(DocumentStatus),
        nullable=False,
        default=DocumentStatus.pending,
        server_default=DocumentStatus.pending.value,
        index=True,
    )

    # --- Set after extraction runs (nullable until then) ---
    extraction_results = Column(JSON, nullable=True)
    confidence_score = Column(Float, nullable=True)

    # --- Human review (nullable until review is triggered/completed) ---
    human_review_required = Column(Boolean, nullable=True)
    human_review_comments = Column(String, nullable=True)   # reviewer's notes

    # Single enum: approved | rejected (null = not yet reviewed)
    human_review_status = Column(Enum(HumanReviewStatus), nullable=True)

    # Only populated when human_review_status == rejected
    human_review_rejection_reason = Column(String, nullable=True)

    # --- Timestamps ---
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))


