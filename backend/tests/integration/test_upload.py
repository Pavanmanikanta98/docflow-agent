"""Test 3: Upload endpoint returns document_id.

Uses an in-memory SQLite database and a mocked Redis client so no
external services are needed."""

import io
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, Enum as SAEnum
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.db import Base


# ---------------------------------------------------------------------------
# Fixtures — in-memory SQLite + mocked Redis
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_engine():
    """Create an in-memory SQLite engine with StaticPool so all
    connections share the same database.

    SQLite lacks native ENUM support so we disable it before creating
    tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Disable native_enum for SQLite compatibility
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, SAEnum):
                col.type.native_enum = False
                col.type.create_constraint = False

    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def test_db(test_engine):
    """Yield a SQLAlchemy session bound to the in-memory engine."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def mock_redis():
    """Return a MagicMock that quacks like a Redis client."""
    r = MagicMock()
    r.setex = MagicMock(return_value=True)
    r.get = MagicMock(return_value=b"fake-file-bytes")
    return r


@pytest.fixture()
def client(test_db, mock_redis):
    """Create a TestClient with dependency overrides for DB and Redis."""

    from backend.api.deps import get_db, get_redis
    from backend.api.main import app

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    def override_get_redis():
        return mock_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    # Patch the ARQ enqueue so it doesn't try to connect to real Redis
    with patch(
        "backend.api.routes.documents.enqueue_process_document",
        new_callable=AsyncMock,
    ):
        yield TestClient(app)

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_upload_returns_document_id(client: TestClient) -> None:
    """POST /api/v1/documents/upload must return a response containing
    a non-empty document_id."""

    fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("test_invoice.pdf", fake_pdf, "application/pdf")},
        data={
            "tenant_id": "test-tenant-001",
            "document_type": "invoice",
        },
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
        data={
            "tenant_id": "test-tenant-002",
            "document_type": "contract",
        },
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


def test_upload_missing_tenant_id_fails(client: TestClient) -> None:
    """Upload without tenant_id should return 422 Unprocessable Entity."""

    fake_pdf = io.BytesIO(b"%PDF-1.4 incomplete upload")

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.pdf", fake_pdf, "application/pdf")},
        data={
            # tenant_id intentionally omitted
            "document_type": "invoice",
        },
    )

    assert response.status_code == 422
