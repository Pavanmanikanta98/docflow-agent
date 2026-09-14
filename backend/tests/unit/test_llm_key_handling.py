"""The server key is the only key.

Callers cannot supply one: an X-LLM-Key header is an ordinary unknown header,
so it buys no rate-limit relief and never reaches the LLM. The key the server
does hold must stay out of os.environ, where any later request could read it.
No real LLM or Redis calls."""

import os
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import middleware
from backend.core.config import settings
from backend.core.llm import llm_client

# ---------------------------------------------------------------------------
# LLM client: keys go to the provider, never into os.environ
# ---------------------------------------------------------------------------

def test_groq_model_with_explicit_key_does_not_touch_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    model = llm_client.get_model(provider="groq", api_key="gsk_test_only")

    assert model is not None
    assert "GROQ_API_KEY" not in os.environ


def test_groq_model_with_server_key_does_not_touch_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(settings, "groq_api_key", "gsk_server_key")

    llm_client.get_model(provider="groq")

    assert "GROQ_API_KEY" not in os.environ


# ---------------------------------------------------------------------------
# Rate limit middleware: no header is a free pass
# ---------------------------------------------------------------------------

class _FakePipeline:
    def __init__(self, store: dict[str, int]) -> None:
        self._store = store
        self._ops: list[tuple[str, str]] = []

    def get(self, key: str) -> "_FakePipeline":
        self._ops.append(("get", key))
        return self

    def incr(self, key: str) -> "_FakePipeline":
        self._ops.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int) -> "_FakePipeline":
        return self

    def execute(self) -> list[Any]:
        results = []
        for op, key in self._ops:
            if op == "get":
                results.append(self._store.get(key))
            else:
                self._store[key] = self._store.get(key, 0) + 1
                results.append(self._store[key])
        return results


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self.store)


def _app_with_zero_limits(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(middleware, "_get_redis", lambda: _FakeRedis())
    monkeypatch.setattr(settings, "rate_limit_per_session", 0)
    app = FastAPI()
    app.add_middleware(middleware.RateLimitMiddleware)

    @app.post("/api/v1/documents/upload")
    async def upload() -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(app)


def test_llm_key_header_does_not_bypass_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The header that used to buy a bypass is now just an unknown header."""
    client = _app_with_zero_limits(monkeypatch)

    response = client.post(
        "/api/v1/documents/upload", headers={"X-LLM-Key": "gsk_user"}
    )

    assert response.status_code == 429
    assert "X-RateLimit-Bypassed" not in response.headers
    assert "own Groq API key" not in response.json()["message"]


def test_upload_is_rate_limited_with_no_special_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _app_with_zero_limits(monkeypatch)

    assert client.post("/api/v1/documents/upload").status_code == 429
