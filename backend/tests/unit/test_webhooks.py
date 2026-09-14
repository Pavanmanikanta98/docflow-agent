"""V1-5: webhooks are signed over timestamp + body, idempotent per event, and never
sent to non-public or non-https hosts. No network: httpx.MockTransport + fake DNS."""

import hashlib
import hmac
import socket
from typing import Any

import httpx
import pytest

from backend.core import connectors
from backend.core.config import settings


def _resolver(ip: str) -> connectors.Resolver:
    def resolve(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]

    return resolve


PUBLIC = _resolver("93.184.215.14")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_signature_matches_documented_recipe() -> None:
    body = b'{"event":"document.completed"}'
    expected = hmac.new(
        b"s3cret", b"1700000000." + body, hashlib.sha256
    ).hexdigest()

    assert connectors.sign("s3cret", "1700000000", body) == expected


def test_signature_changes_when_timestamp_changes() -> None:
    body = b"{}"
    assert connectors.sign("k", "1", body) != connectors.sign("k", "2", body)


def test_idempotency_key_is_stable_per_document_and_event() -> None:
    key = connectors.idempotency_key

    assert key(7, "document.approved") == key(7, "document.approved")
    assert key(7, "document.approved") != key(7, "document.completed")


# ---------------------------------------------------------------------------
# URL validation (SSRF guard)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("url", "ip"),
    [
        ("http://hooks.example.com/x", "93.184.215.14"),  # not https
        ("https://127.0.0.1/x", "127.0.0.1"),  # loopback
        ("https://169.254.169.254/latest/meta-data", "169.254.169.254"),  # metadata
        ("https://10.0.0.5/x", "10.0.0.5"),  # private
        ("https://internal.example.com/x", "192.168.1.10"),  # public name, private IP
        ("https://[::1]/x", "::1"),  # IPv6 loopback
        ("https://mapped.example.com/x", "::ffff:127.0.0.1"),  # IPv4-mapped loopback
    ],
)
def test_rejects_non_public_or_non_https_urls(url: str, ip: str) -> None:
    with pytest.raises(connectors.WebhookURLRejectedError):
        connectors.validate_webhook_url(url, resolver=_resolver(ip))


def test_accepts_public_https_url() -> None:
    connectors.validate_webhook_url(
        "https://hooks.example.com/docflow", resolver=PUBLIC
    )


# ---------------------------------------------------------------------------
# dispatch_webhook
# ---------------------------------------------------------------------------

@pytest.fixture()
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "webhooks_enabled", True)
    monkeypatch.setattr(settings, "webhook_secret", "test-secret")


def _recording_client(
    requests: list[httpx.Request], status: int = 200
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _send(
    client: httpx.AsyncClient,
    url: str = "https://hooks.example.com/x",
    resolver: connectors.Resolver = PUBLIC,
) -> connectors.WebhookResult:
    return await connectors.dispatch_webhook(
        document_id=42,
        event="document.completed",
        payload={"document_id": 42, "status": "completed"},
        url=url,
        client=client,
        resolver=resolver,
    )


async def test_sends_signed_request_that_receiver_can_verify(enabled: None) -> None:
    requests: list[httpx.Request] = []
    async with _recording_client(requests) as client:
        result = await _send(client)

    assert result.delivered is True
    sent = requests[0]
    timestamp = sent.headers["X-Timestamp"]
    expected = hmac.new(
        b"test-secret", timestamp.encode() + b"." + sent.content, hashlib.sha256
    ).hexdigest()
    assert hmac.compare_digest(sent.headers["X-DocFlow-Signature"], expected)


async def test_resending_the_same_event_reuses_the_idempotency_key(
    enabled: None,
) -> None:
    requests: list[httpx.Request] = []
    async with _recording_client(requests) as client:
        await _send(client)
        await _send(client)

    keys = {r.headers["X-Idempotency-Key"] for r in requests}
    assert keys == {"doc-42-document.completed"}


async def test_nothing_is_sent_when_webhooks_are_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "webhooks_enabled", False)
    requests: list[httpx.Request] = []
    async with _recording_client(requests) as client:
        result = await _send(client)

    assert result.delivered is False
    assert requests == []


async def test_nothing_is_sent_without_a_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "webhooks_enabled", True)
    monkeypatch.setattr(settings, "webhook_secret", "")
    requests: list[httpx.Request] = []
    async with _recording_client(requests) as client:
        result = await _send(client)

    assert result.error == "missing WEBHOOK_SECRET"
    assert requests == []


async def test_nothing_is_sent_to_a_private_address(enabled: None) -> None:
    requests: list[httpx.Request] = []
    async with _recording_client(requests) as client:
        result = await _send(client, resolver=_resolver("10.0.0.5"))

    assert result.delivered is False
    assert requests == []


async def test_receiver_error_is_reported_not_raised(enabled: None) -> None:
    requests: list[httpx.Request] = []
    async with _recording_client(requests, status=500) as client:
        result = await _send(client)

    assert result.delivered is False
    assert result.status_code == 500
