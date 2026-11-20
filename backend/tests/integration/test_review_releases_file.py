"""Issue #56: approving or rejecting a document deletes its buffered file."""

import io

import pytest
from fastapi.testclient import TestClient

from backend.models.db import Document, DocumentStatus
from backend.tests.integration.conftest import SESSION_A, session_headers


def _upload_held_for_review(client: TestClient, test_db) -> int:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("a.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
        data={"document_type": "invoice"},
        headers=session_headers(SESSION_A),
    )
    document_id = int(response.json()["document_id"])
    doc = test_db.get(Document, document_id)
    doc.status = DocumentStatus.awaiting_review
    doc.confidence_score = 0.4
    test_db.commit()
    return document_id


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_a_review_decision_deletes_the_buffered_file(
    client: TestClient, test_db, mock_redis, decision: str
) -> None:
    document_id = _upload_held_for_review(client, test_db)

    response = client.post(
        f"/api/v1/documents/{document_id}/review",
        json={
            "job_id": str(document_id),
            "human_review_status": decision,
            "human_review_rejection_reason": (
                "wrong total" if decision == "rejected" else None
            ),
        },
        headers=session_headers(SESSION_A),
    )

    assert response.status_code == 200, response.text
    mock_redis.delete.assert_called_with(f"doc_bytes:{document_id}")
