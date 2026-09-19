"""The usage badge must show the count the rate limiter is enforcing.

The middleware counts uploads under the X-Session-Id header, and GET /usage
reads the count back for the navbar badge. If the two ever key the counter
differently, the badge shows 0 used while the visitor is being throttled."""

import io
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.tests.integration.conftest import (
    SESSION_A,
    SESSION_B,
    session_headers,
)


class _CountingRedis:
    """Just enough of a Redis client for the rate limiter and the usage route.

    Inside ``pipeline()`` calls are queued and run by ``execute()``, as the
    middleware expects; outside one, ``get`` reads the counter directly, as the
    usage route expects."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self._queued: list[tuple[str, str]] | None = None

    def pipeline(self) -> "_CountingRedis":
        self._queued = []
        return self

    def get(self, key: str) -> Any:
        if self._queued is not None:
            self._queued.append(("get", key))
            return self
        return self._read(key)

    def incr(self, key: str) -> "_CountingRedis":
        self._queued.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int) -> "_CountingRedis":
        self._queued.append(("expire", key))
        return self

    def execute(self) -> list[Any]:
        results: list[Any] = []
        for op, key in self._queued or []:
            if op == "incr":
                self.counters[key] = self.counters.get(key, 0) + 1
                results.append(self.counters[key])
            elif op == "get":
                results.append(self._read(key))
            else:
                results.append(True)
        self._queued = None
        return results

    def _read(self, key: str) -> bytes | None:
        value = self.counters.get(key)
        return None if value is None else str(value).encode()


@pytest.fixture()
def counting_redis(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> _CountingRedis:
    """One counter store shared by the rate limiter and the usage route."""
    from backend.api import middleware
    from backend.api.routes import usage

    store = _CountingRedis()
    monkeypatch.setattr(middleware, "_get_redis", lambda: store)
    monkeypatch.setattr(usage, "redis_client", store)
    return store


def _upload_as(client: TestClient, session_id: str) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("invoice.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        data={"document_type": "invoice"},
        headers=session_headers(session_id),
    )
    assert response.status_code == 200, response.text


def test_usage_reports_the_callers_own_upload_count(
    client: TestClient, counting_redis: _CountingRedis
) -> None:
    _upload_as(client, SESSION_A)
    _upload_as(client, SESSION_A)
    _upload_as(client, SESSION_B)

    usage_a = client.get("/api/v1/usage", headers=session_headers(SESSION_A)).json()
    usage_b = client.get("/api/v1/usage", headers=session_headers(SESSION_B)).json()

    assert usage_a["used"] == 2
    assert usage_a["remaining"] == usage_a["limit"] - 2
    assert usage_b["used"] == 1


def test_usage_ignores_a_session_id_in_the_query_string(
    client: TestClient, counting_redis: _CountingRedis
) -> None:
    """The old badge sent ?session_id=. Naming another session there must not
    return that session's count."""
    _upload_as(client, SESSION_B)

    response = client.get(
        f"/api/v1/usage?session_id={SESSION_B}", headers=session_headers(SESSION_A)
    )

    assert response.json()["used"] == 0
