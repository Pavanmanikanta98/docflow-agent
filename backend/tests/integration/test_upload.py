"""Test 3: Upload endpoint returns document_id.

Fixtures live in conftest.py — in-memory SQLite and a mocked Redis client,
so no external services are needed."""

import io
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.tests.integration.conftest import SESSION_A, session_headers


def test_upload_returns_document_id(client: TestClient) -> None:
    """POST /api/v1/documents/upload must return a response containing
    a non-empty document_id."""

    fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("test_invoice.pdf", fake_pdf, "application/pdf")},
        data={"document_type": "invoice"},
        headers=session_headers(),
    )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )

    body = response.json()

    assert "document_id" in body, f"Response missing 'document_id': {body}"
    assert body["document_id"], "document_id must not be empty"
    assert body["status"] == "pending"
    assert body["document_type"] == "invoice"


def test_upload_returns_correct_metadata(client: TestClient) -> None:
    """Verify the full response shape from upload matches the schema."""

    fake_pdf = io.BytesIO(b"%PDF-1.4 another fake file")

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("contract.pdf", fake_pdf, "application/pdf")},
        data={"document_type": "contract"},
        headers=session_headers(),
    )

    assert response.status_code == 200
    body = response.json()

    # All required fields from DocumentUploadResponse must be present
    required_keys = [
        "job_id", "status", "document_type", "document_id",
        "document_size", "document_mime_type",
    ]
    for key in required_keys:
        assert key in body, f"Missing key '{key}' in response"

    assert body["document_mime_type"] == "application/pdf"
    assert body["document_size"] > 0


def test_upload_without_a_session_header_is_rejected(client: TestClient) -> None:
    """No X-Session-Id means no identity, so there is nothing to file the
    document under. Rejected before anything is stored."""

    fake_pdf = io.BytesIO(b"%PDF-1.4 incomplete upload")

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.pdf", fake_pdf, "application/pdf")},
        data={"document_type": "invoice"},
    )

    assert response.status_code == 400


def test_upload_ignores_a_tenant_id_in_the_form(client: TestClient) -> None:
    """The document belongs to the caller's session, never to a tenant the
    caller names in the upload form."""

    fake_pdf = io.BytesIO(b"%PDF-1.4 spoof attempt")

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("inv.pdf", fake_pdf, "application/pdf")},
        data={"document_type": "invoice", "tenant_id": "somebody-elses-tenant"},
        headers=session_headers(),
    )

    assert response.status_code == 200
    document_id = response.json()["document_id"]

    # The uploader can still read it back, so it was filed under their session.
    mine = client.get(
        f"/api/v1/documents/{document_id}", headers=session_headers()
    )
    assert mine.status_code == 200


def test_upload_never_stores_an_llm_key_header(
    client: TestClient, mock_redis: MagicMock
) -> None:
    """Callers cannot supply a key: the header is read by nothing and stored nowhere."""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("inv.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
        data={"document_type": "invoice"},
        headers={**session_headers(), "X-LLM-Key": "gsk_should_not_be_stored"},
    )

    assert response.status_code == 200
    stored_keys = [c.args[0] for c in mock_redis.setex.call_args_list]
    assert not any(k.startswith("llm_key:") for k in stored_keys)


def test_upload_rejects_webhook_url_when_webhooks_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.core.config import settings

    monkeypatch.setattr(settings, "webhooks_enabled", False)

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("inv.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
        data={
            "document_type": "invoice",
            "webhook_url": "https://hooks.example.com/x",
        },
        headers=session_headers(),
    )

    assert response.status_code == 422
    assert "disabled" in response.json()["detail"]


def test_upload_rejects_private_webhook_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.core.config import settings

    monkeypatch.setattr(settings, "webhooks_enabled", True)

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("inv.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
        data={
            "document_type": "invoice",
            "webhook_url": "https://169.254.169.254/latest/meta-data",
        },
        headers=session_headers(SESSION_A),
    )

    assert response.status_code == 422
