"""One visitor must not be able to reach another visitor's document.

The demo has no login. Every browser mints a session id and sends it as
X-Session-Id, and the server files each document under that id. These tests
upload as one session and then try every document route as a second session.

A stranger gets 404 rather than 403 on all of them, so the response does not
confirm that the document id exists."""

import io

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models.db import Document, DocumentStatus, HumanReviewStatus
from backend.tests.integration.conftest import (
    SESSION_A,
    SESSION_B,
    session_headers,
)


def _upload_as(client: TestClient, session_id: str) -> int:
    """Upload one document as the given session and return its id."""
    response = client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "invoice.pdf",
                io.BytesIO(b"%PDF-1.4 owned content"),
                "application/pdf",
            )
        },
        data={"document_type": "invoice"},
        headers=session_headers(session_id),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["document_id"])


def _mark_processed(
    test_db: Session, document_id: int, status: DocumentStatus
) -> None:
    """Leave the row as the worker would: a finished status and a score.

    The validator always returns a float confidence (validator.py), so a row
    with a finished status and no score is not a state the pipeline produces.
    """
    doc = test_db.get(Document, document_id)
    doc.status = status
    doc.confidence_score = 0.91
    doc.extraction_results = {"invoice_number": "INV-1"}
    test_db.commit()


# ---------------------------------------------------------------------------
# A second session cannot reach the first session's document
# ---------------------------------------------------------------------------

def test_another_session_cannot_read_a_document(client: TestClient) -> None:
    document_id = _upload_as(client, SESSION_A)

    response = client.get(
        f"/api/v1/documents/{document_id}", headers=session_headers(SESSION_B)
    )

    assert response.status_code == 404


def test_another_session_cannot_download_the_file(client: TestClient) -> None:
    document_id = _upload_as(client, SESSION_A)

    response = client.get(
        f"/api/v1/documents/{document_id}/file",
        headers=session_headers(SESSION_B),
    )

    assert response.status_code == 404


def test_another_session_cannot_export_a_document(
    client: TestClient, test_db: Session
) -> None:
    document_id = _upload_as(client, SESSION_A)

    # Export only serves completed documents, so finish this one first —
    # otherwise the status gate would hide whether ownership was checked.
    _mark_processed(test_db, document_id, DocumentStatus.completed)

    assert client.get(
        f"/api/v1/documents/{document_id}/export",
        headers=session_headers(SESSION_A),
    ).status_code == 200

    response = client.get(
        f"/api/v1/documents/{document_id}/export",
        headers=session_headers(SESSION_B),
    )

    assert response.status_code == 404


def test_another_session_cannot_approve_a_document(
    client: TestClient, test_db: Session
) -> None:
    """The one route that changes state — and approving fires the owner's
    webhook, so a stranger must not reach it."""
    document_id = _upload_as(client, SESSION_A)

    _mark_processed(test_db, document_id, DocumentStatus.awaiting_review)

    response = client.post(
        f"/api/v1/documents/{document_id}/review",
        json={
            "job_id": str(document_id),
            "human_review_status": "approved",
            "review_comments": "not mine to approve",
        },
        headers=session_headers(SESSION_B),
    )

    assert response.status_code == 404

    test_db.expire_all()
    doc = test_db.get(Document, document_id)
    assert doc.status == DocumentStatus.awaiting_review
    assert doc.human_review_status is None
    assert doc.human_review_comments is None


def test_the_list_only_shows_your_own_documents(client: TestClient) -> None:
    mine = _upload_as(client, SESSION_A)
    theirs = _upload_as(client, SESSION_B)

    listed = client.get("/api/v1/documents", headers=session_headers(SESSION_A))

    assert listed.status_code == 200
    body = listed.json()
    ids = [int(d["id"]) for d in body["documents"]]
    assert ids == [mine]
    assert theirs not in ids
    assert body["total"] == 1


# ---------------------------------------------------------------------------
# The owner still gets through
# ---------------------------------------------------------------------------

def test_the_owning_session_can_read_and_approve(
    client: TestClient, test_db: Session
) -> None:
    """The isolation must not lock the owner out of their own document."""
    document_id = _upload_as(client, SESSION_A)

    _mark_processed(test_db, document_id, DocumentStatus.awaiting_review)

    assert client.get(
        f"/api/v1/documents/{document_id}", headers=session_headers(SESSION_A)
    ).status_code == 200

    assert client.get(
        f"/api/v1/documents/{document_id}/file", headers=session_headers(SESSION_A)
    ).status_code == 200

    approved = client.post(
        f"/api/v1/documents/{document_id}/review",
        json={
            "job_id": str(document_id),
            "human_review_status": "approved",
            "review_comments": "looks right",
        },
        headers=session_headers(SESSION_A),
    )

    assert approved.status_code == 200

    test_db.expire_all()
    doc = test_db.get(Document, document_id)
    assert doc.human_review_status == HumanReviewStatus.approved


# ---------------------------------------------------------------------------
# A missing or junk session id is refused outright
# ---------------------------------------------------------------------------

def test_every_document_route_needs_a_session_header(client: TestClient) -> None:
    document_id = _upload_as(client, SESSION_A)

    unauthenticated = [
        client.get("/api/v1/documents"),
        client.get(f"/api/v1/documents/{document_id}"),
        client.get(f"/api/v1/documents/{document_id}/file"),
        client.get(f"/api/v1/documents/{document_id}/export"),
        client.post(
            f"/api/v1/documents/{document_id}/review",
            json={"job_id": str(document_id), "human_review_status": "approved"},
        ),
        client.get("/api/v1/usage"),
    ]

    assert [r.status_code for r in unauthenticated] == [400] * 6


def test_a_too_short_session_id_is_refused(client: TestClient) -> None:
    """Seven characters is not one of our session ids, so it is not an
    identity we will file or fetch documents under."""
    response = client.get(
        "/api/v1/documents", headers=session_headers("ses_123")
    )

    assert response.status_code == 400
