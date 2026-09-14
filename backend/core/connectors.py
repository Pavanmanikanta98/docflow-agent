"""Outbound webhooks: signed, idempotent, and limited to public HTTPS hosts.

Signature recipe (receivers can verify it):
    signature = HMAC_SHA256(WEBHOOK_SECRET, f"{X-Timestamp}.{raw_body}").hexdigest()
    header    = X-DocFlow-Signature: <signature>

X-Idempotency-Key is stable per document + event, so a re-send of the same
event carries the same key and the receiver can drop duplicates.

Known limit: the URL is resolved and checked before sending, and redirects are
not followed, but a host that changes its DNS answer between the check and the
request (DNS rebinding) is not fully prevented.
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

Resolver = Callable[..., list[tuple[Any, ...]]]


class WebhookURLRejectedError(ValueError):
    """The webhook URL is not allowed (scheme, host, or resolved address)."""


@dataclass(frozen=True)
class WebhookResult:
    delivered: bool
    status_code: int | None = None
    error: str | None = None


def idempotency_key(document_id: int, event: str) -> str:
    """Same document + same event → same key, on every attempt."""
    return f"doc-{document_id}-{event}"


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """HMAC-SHA256 over `timestamp.body`, hex encoded."""
    message = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def validate_webhook_url(url: str, resolver: Resolver = socket.getaddrinfo) -> None:
    """Allow only https URLs whose host resolves to public IP addresses.

    Raises:
        WebhookURLRejectedError: for non-https URLs, missing hosts, unresolvable hosts,
            or any resolved address that is private, loopback, link-local or reserved.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise WebhookURLRejectedError("Webhook URL must use https")
    host = parsed.hostname
    if not host:
        raise WebhookURLRejectedError("Webhook URL has no host")

    try:
        infos = resolver(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise WebhookURLRejectedError(
            f"Webhook host {host!r} cannot be resolved"
        ) from exc

    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if not address.is_global:
            raise WebhookURLRejectedError(
                f"Webhook host {host!r} resolves to a non-public address"
            )


def _encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


async def dispatch_webhook(
    *,
    document_id: int,
    event: str,
    payload: dict[str, Any],
    url: str,
    client: httpx.AsyncClient | None = None,
    resolver: Resolver = socket.getaddrinfo,
) -> WebhookResult:
    """Send one signed webhook. Never raises; failures are logged and returned."""
    host = urlparse(url).hostname or "?"

    if not settings.webhooks_enabled:
        return WebhookResult(delivered=False, error="webhooks disabled")
    if not settings.webhook_secret:
        logger.error(
            "Webhook not sent for document %s: WEBHOOK_SECRET is empty", document_id
        )
        return WebhookResult(delivered=False, error="missing WEBHOOK_SECRET")

    try:
        validate_webhook_url(url, resolver=resolver)
    except WebhookURLRejectedError as exc:
        logger.warning(
            "Webhook rejected for document %s (%s): %s", document_id, host, exc
        )
        return WebhookResult(delivered=False, error=str(exc))

    body = _encode({"event": event, **payload})
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "X-DocFlow-Signature": sign(settings.webhook_secret, timestamp, body),
        "X-Timestamp": timestamp,
        "X-Idempotency-Key": idempotency_key(document_id, event),
    }

    owns_client = client is None
    http = client or httpx.AsyncClient(
        timeout=settings.webhook_timeout_seconds, follow_redirects=False
    )
    try:
        response = await http.post(url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning(
            "Webhook to %s failed for document %s: %s", host, document_id, exc
        )
        return WebhookResult(delivered=False, error=type(exc).__name__)
    finally:
        if owns_client:
            await http.aclose()

    if response.is_success:
        return WebhookResult(delivered=True, status_code=response.status_code)
    logger.warning(
        "Webhook to %s for document %s returned HTTP %s",
        host,
        document_id,
        response.status_code,
    )
    return WebhookResult(delivered=False, status_code=response.status_code)
