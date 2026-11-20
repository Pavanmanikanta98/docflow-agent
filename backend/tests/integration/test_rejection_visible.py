"""Issue #57: a rejected document says so, in the list and in the detail.

A rejection keeps the status `awaiting_review` (a new status would be a
schema change); `human_review_status` and the reason are what the screens
read to show it."""

import io

from fastapi.testclient import TestClient

from backend.models.db import Document, DocumentStatus
from backend.tests.integration.conftest import SESSION_A, session_headers


def test_rejected_document_carries_its_decision_and_reason(
    client: TestClient, test_db
) -> None:
    headers = session_headers(SESSION_A)
    upload = client.post(
        "/api/v1/documents/upload",
        files={"file": ("a.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
        data={"document_type": "invoice"},
        headers=headers,
    )
    document_id = int(upload.json()["document_id"])
    doc = test_db.get(Document, document_id)
    doc.status = DocumentStatus.awaiting_review
    doc.confidence_score = 0.4  # the pipeline always sets one
    test_db.commit()

    client.post(
        f"/api/v1/documents/{document_id}/review",
        json={
            "job_id": str(document_id),
            "human_review_status": "rejected",
            "human_review_rejection_reason": "Total does not match",
        },
        headers=headers,
    )

    detail = client.get(f"/api/v1/documents/{document_id}", headers=headers).json()
    listed = client.get("/api/v1/documents", headers=headers).json()["documents"][0]
    for shown in (detail, listed):
        assert shown["status"] == "awaiting_review"
        assert shown["human_review_status"] == "rejected"
        assert shown["human_review_rejection_reason"] == "Total does not match"
