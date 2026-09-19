"""Shared fixtures for the integration tests.

An in-memory SQLite database and a mocked Redis client, so the suite needs no
external services."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Enum as SAEnum
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.db import Base

# Two browsers. Shaped like the ids the frontend mints — "ses_" plus 16 hex
# characters (frontend/lib/api.ts).
SESSION_A = "ses_a1b2c3d4e5f60718"
SESSION_B = "ses_99887766554433aa"


def session_headers(session_id: str = SESSION_A) -> dict[str, str]:
    """The header a browser sends on every request; the caller's whole identity."""
    return {"X-Session-Id": session_id}


class _AllowAllRedis:
    """Rate-limit Redis stand-in: every counter reads 0."""

    def __init__(self) -> None:
        self._queued = 0

    def pipeline(self) -> "_AllowAllRedis":
        self._queued = 0
        return self

    def get(self, key: str) -> "_AllowAllRedis":
        self._queued += 1
        return self

    def incr(self, key: str) -> "_AllowAllRedis":
        self._queued += 1
        return self

    def expire(self, key: str, ttl: int) -> "_AllowAllRedis":
        self._queued += 1
        return self

    def execute(self) -> list[None]:
        return [None] * self._queued


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
    testing_session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine,
    )
    session = testing_session_local()
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
def client(test_db, mock_redis, monkeypatch: pytest.MonkeyPatch):
    """Create a TestClient with dependency overrides for DB and Redis.

    RateLimitMiddleware bypasses the ``get_redis`` dependency and reads the
    module-level client via ``middleware._get_redis``, so that is patched too;
    every request still runs through the real middleware, just without a
    Redis server."""

    from backend.api import middleware
    from backend.api.deps import get_db, get_redis
    from backend.api.main import app

    monkeypatch.setattr(middleware, "_get_redis", lambda: _AllowAllRedis())

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
