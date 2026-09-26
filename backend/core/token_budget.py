"""ADR 006 — a Redis-backed token budget in front of the LLM.

Groq's free tier enforces four independent ceilings per model: tokens per
minute (TPM), requests per minute (RPM), tokens per day (TPD) and requests
per day (RPD). A request that would cross any of them is rejected outright
(HTTP 429) rather than queued by Groq itself.

This module makes running out of capacity a WAIT, not a FAILURE:
  - `estimate_tokens` sizes a request before it is sent.
  - `TokenBudget.reserve` grants or defers a request against all four
    ceilings, atomically, via a Lua script (so two workers racing the same
    model never both believe they got the last slot).
  - `TokenBudget.settle` reconciles the estimate against the real usage
    reported by the API once the call completes.
  - `TokenBudget.sync_from_headers` corrects our tracked usage from Groq's
    own `x-ratelimit-*` response headers, so drift (another process, a
    slightly-off estimate) self-heals on every call.
  - `TokenBudget.set_cooldown_from_retry_after` / `cooldown_remaining` back a
    single GLOBAL cooldown key: a 429 on one model means the shared window is
    exhausted, so every reservation waits it out together.

Header names and their duration format ("1m26.4s", "585ms") were confirmed
against a live response from api.groq.com on 2026-09-24, not guessed from
docs (see ADR 006).
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Mapping

import tiktoken

# The closest public tiktoken encoding to modern OSS/GPT-family tokenizers.
# Groq does not publish exact tokenizer parity for gpt-oss models, so this is
# an estimate used for pre-flight sizing, not a claim of an exact match —
# `settle()` reconciles it against the API's own reported usage afterward.
TIKTOKEN_ENCODING = "o200k_base"

_GLOBAL_COOLDOWN_KEY = "token_budget:cooldown"

# Fixed per-message overhead tiktoken's chat-format guidance uses for
# OpenAI-style chat messages (role + separators); applied per message so the
# estimate does not undercount a many-message conversation.
_TOKENS_PER_MESSAGE_OVERHEAD = 4


def _encoding():
    return tiktoken.get_encoding(TIKTOKEN_ENCODING)


def estimate_tokens(
    messages: list[Mapping[str, str]], max_completion_tokens: int
) -> int:
    """Estimate the total tokens a chat request will consume.

    Includes the prompt (all messages) AND the reply budget
    (`max_completion_tokens`), because both count against TPM/TPD — a
    request is not "cheap" just because the model might reply briefly.
    """
    enc = _encoding()
    total = 0
    for message in messages:
        total += _TOKENS_PER_MESSAGE_OVERHEAD
        for value in message.values():
            total += len(enc.encode(str(value)))
    return total + max_completion_tokens


def _parse_groq_duration(value: str) -> float:
    """Parse Groq's duration strings ("1m26.4s", "585ms", "7.66s") to seconds.

    Order matters: "ms" must be tried before "m" and "s" individually, or
    "585ms" would wrongly parse as "58" minutes + a dangling "5ms".
    Returns 0.0 for a value that does not match (never raises — a header we
    cannot parse should not crash the caller; the bucket's own tracking
    remains authoritative).
    """
    pattern = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
    seconds = 0.0
    matched = False
    for amount, unit in pattern.findall(value):
        matched = True
        n = float(amount)
        if unit == "h":
            seconds += n * 3600
        elif unit == "m":
            seconds += n * 60
        elif unit == "s":
            seconds += n
        elif unit == "ms":
            seconds += n / 1000
    return seconds if matched else 0.0


@dataclass(frozen=True)
class Reservation:
    """A granted slot against one model's budget, pending settlement."""

    id: str
    model: str
    estimated_tokens: int
    tpm_key: str
    tpd_key: str


@dataclass(frozen=True)
class ReserveResult:
    granted: bool
    wait_seconds: float
    reservation: Reservation | None


# KEYS[1..4] = tpm_key, rpm_key, tpd_key, rpd_key
# ARGV[1..4] = tpm_limit, rpm_limit, tpd_limit, rpd_limit
# ARGV[5]    = estimated_tokens
# ARGV[6..9] = tpm_ttl_ms, rpm_ttl_ms, tpd_ttl_ms, rpd_ttl_ms
# Returns {granted(0/1), wait_ms}
_RESERVE_SCRIPT = """
local tpm_used = tonumber(redis.call('GET', KEYS[1]) or '0')
local rpm_used = tonumber(redis.call('GET', KEYS[2]) or '0')
local tpd_used = tonumber(redis.call('GET', KEYS[3]) or '0')
local rpd_used = tonumber(redis.call('GET', KEYS[4]) or '0')

local tpm_limit = tonumber(ARGV[1])
local rpm_limit = tonumber(ARGV[2])
local tpd_limit = tonumber(ARGV[3])
local rpd_limit = tonumber(ARGV[4])
local est = tonumber(ARGV[5])

if tpm_used + est > tpm_limit then
  return {0, tonumber(ARGV[6])}
end
if rpm_used + 1 > rpm_limit then
  return {0, tonumber(ARGV[7])}
end
if tpd_used + est > tpd_limit then
  return {0, tonumber(ARGV[8])}
end
if rpd_used + 1 > rpd_limit then
  return {0, tonumber(ARGV[9])}
end

redis.call('INCRBY', KEYS[1], est)
redis.call('PEXPIRE', KEYS[1], ARGV[6])
redis.call('INCRBY', KEYS[2], 1)
redis.call('PEXPIRE', KEYS[2], ARGV[7])
redis.call('INCRBY', KEYS[3], est)
redis.call('PEXPIRE', KEYS[3], ARGV[8])
redis.call('INCRBY', KEYS[4], 1)
redis.call('PEXPIRE', KEYS[4], ARGV[9])

return {1, 0}
"""


class TokenBudget:
    """Per-model rate-limit tracker backed by Redis fixed-window counters.

    Each model gets its own four counters (TPM/RPM/TPD/RPD), keyed by a
    window index derived from wall-clock time, so a counter naturally
    disappears (via TTL) once its window has passed rather than needing an
    explicit reset job.
    """

    def __init__(
        self,
        redis_client,
        model: str,
        tpm: int,
        rpm: int,
        tpd: int,
        rpd: int,
        now_fn=time.time,
    ) -> None:
        self._redis = redis_client
        self.model = model
        self.tpm = tpm
        self.rpm = rpm
        self.tpd = tpd
        self.rpd = rpd
        self._now = now_fn
        self._script = redis_client.register_script(_RESERVE_SCRIPT)

    def _key(self, kind: str, bucket: int) -> str:
        return f"token_budget:{self.model}:{kind}:{bucket}"

    def cooldown_remaining(self) -> float:
        """Seconds left on the GLOBAL cooldown, or 0.0 if none is active."""
        ttl_ms = self._redis.pttl(_GLOBAL_COOLDOWN_KEY)
        # pttl returns -2 (key absent) or -1 (no TTL, shouldn't happen here)
        if ttl_ms is None or ttl_ms < 0:
            return 0.0
        return ttl_ms / 1000

    def set_cooldown(self, seconds: float) -> None:
        """Set the global cooldown, shared by every model's budget."""
        if seconds <= 0:
            return
        self._redis.set(_GLOBAL_COOLDOWN_KEY, "1", px=int(seconds * 1000))

    def set_cooldown_from_retry_after(self, headers: Mapping[str, str]) -> None:
        """Read a 429 response's `retry-after` header and set the cooldown.

        `retry-after` is a standard HTTP header (RFC 9110), normally a plain
        integer number of seconds. Groq's OpenAI-compatible error responses
        follow that convention; if a value ever arrives in Groq's other
        duration format instead, this falls back to parsing it the same way
        as the ratelimit headers rather than dropping it.
        """
        value = _get_header(headers, "retry-after")
        if value is None:
            return
        try:
            seconds = float(value)
        except ValueError:
            seconds = _parse_groq_duration(value)
        self.set_cooldown(seconds)

    def reserve(self, estimated_tokens: int) -> ReserveResult:
        """Ask for a slot for a request of this estimated size.

        Checks the global cooldown first — if it is active, every model
        waits, without even touching the per-model counters.
        """
        cooldown = self.cooldown_remaining()
        if cooldown > 0:
            return ReserveResult(granted=False, wait_seconds=cooldown, reservation=None)

        now = self._now()
        minute_bucket = int(now // 60)
        day_bucket = int(now // 86400)

        tpm_key = self._key("tpm", minute_bucket)
        rpm_key = self._key("rpm", minute_bucket)
        tpd_key = self._key("tpd", day_bucket)
        rpd_key = self._key("rpd", day_bucket)

        minute_ttl_ms = int(((minute_bucket + 1) * 60 - now) * 1000) + 1000
        day_ttl_ms = int(((day_bucket + 1) * 86400 - now) * 1000) + 1000

        granted, wait_ms = self._script(
            keys=[tpm_key, rpm_key, tpd_key, rpd_key],
            args=[
                self.tpm,
                self.rpm,
                self.tpd,
                self.rpd,
                estimated_tokens,
                minute_ttl_ms,
                minute_ttl_ms,
                day_ttl_ms,
                day_ttl_ms,
            ],
        )

        if not granted:
            return ReserveResult(
                granted=False, wait_seconds=max(wait_ms, 0) / 1000, reservation=None
            )

        reservation = Reservation(
            id=uuid.uuid4().hex,
            model=self.model,
            estimated_tokens=estimated_tokens,
            tpm_key=tpm_key,
            tpd_key=tpd_key,
        )
        return ReserveResult(granted=True, wait_seconds=0.0, reservation=reservation)

    def settle(self, reservation: Reservation, actual_tokens: int) -> None:
        """Reconcile a reservation's estimate against the real usage.

        The delta (positive or negative) is applied to the same window
        counters the reservation incremented. If the window has since
        rolled over (the keys expired), the INCRBY recreates them at the
        delta — harmless, since that window is no longer being checked
        against by new reservations anyway.
        """
        delta = actual_tokens - reservation.estimated_tokens
        if delta == 0:
            return
        self._redis.incrby(reservation.tpm_key, delta)
        self._redis.incrby(reservation.tpd_key, delta)

    def sync_from_headers(self, headers: Mapping[str, str]) -> None:
        """Correct tracked usage from Groq's own `x-ratelimit-*` headers.

        Confirmed live on 2026-09-24 against api.groq.com:
            x-ratelimit-limit-requests, x-ratelimit-limit-tokens,
            x-ratelimit-remaining-requests, x-ratelimit-remaining-tokens,
            x-ratelimit-reset-requests, x-ratelimit-reset-tokens
        reset-* values are duration strings ("1m26.4s", "585ms"), not plain
        seconds.

        This overwrites (SET, not INCRBY) the CURRENT minute-window
        counters with Groq's own view, so drift from our estimate — or from
        another process sharing the same key — cannot compound.
        """
        limit_tokens = _get_int_header(headers, "x-ratelimit-limit-tokens")
        remaining_tokens = _get_int_header(headers, "x-ratelimit-remaining-tokens")
        limit_requests = _get_int_header(headers, "x-ratelimit-limit-requests")
        remaining_requests = _get_int_header(headers, "x-ratelimit-remaining-requests")
        reset_tokens = _get_header(headers, "x-ratelimit-reset-tokens")
        reset_requests = _get_header(headers, "x-ratelimit-reset-requests")

        now = self._now()
        minute_bucket = int(now // 60)

        if limit_tokens is not None and remaining_tokens is not None:
            used = max(limit_tokens - remaining_tokens, 0)
            ttl_ms = int(_parse_groq_duration(reset_tokens or "0s") * 1000) + 1000
            self._redis.set(self._key("tpm", minute_bucket), used, px=max(ttl_ms, 1000))

        if limit_requests is not None and remaining_requests is not None:
            used = max(limit_requests - remaining_requests, 0)
            ttl_ms = int(_parse_groq_duration(reset_requests or "0s") * 1000) + 1000
            self._redis.set(self._key("rpm", minute_bucket), used, px=max(ttl_ms, 1000))


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive header lookup that works for a plain dict too."""
    if hasattr(headers, "get"):
        value = headers.get(name)
        if value is not None:
            return value
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _get_int_header(headers: Mapping[str, str], name: str) -> int | None:
    value = _get_header(headers, name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


class CapacityWaitError(Exception):
    """Raised when a reservation cannot be granted right now.

    The worker catches this and defers the ARQ job instead of failing the
    document — see `backend/queue/worker.py`.
    """

    def __init__(self, wait_seconds: float, model: str):
        self.wait_seconds = wait_seconds
        self.model = model
        super().__init__(
            f"No capacity for model {model!r}: retry in {wait_seconds:.1f}s"
        )


class RequestTooLargeError(Exception):
    """Raised when a single request's own size exceeds TPM outright.

    Distinct from CapacityWaitError on purpose: a request bigger than the
    entire per-minute ceiling can never be granted no matter how long the
    caller waits, so retrying it is not "capacity is temporarily busy" —
    it is a genuine failure. This is the one case ADR 006's chunker cannot
    fully prevent: a single page whose own text already exceeds the budget
    (backend.core.chunking.split_pages_into_chunks still gives it its own
    chunk rather than dropping it, since that chunk might still fit after a
    future TPM increase, but it cannot fit today).
    """

    def __init__(self, estimated_tokens: int, tpm: int, model: str):
        self.estimated_tokens = estimated_tokens
        self.tpm = tpm
        self.model = model
        super().__init__(
            f"Request for {estimated_tokens} tokens exceeds the {tpm} TPM "
            f"ceiling for model {model!r} outright — no wait makes it fit."
        )


def get_budget_for_model(redis_client, model: str) -> TokenBudget:
    """Build a TokenBudget for `model` from the configured settings.

    All models currently share the same configured ceilings (the free-tier
    numbers by default); the bucket state itself is still tracked
    independently per model, so raising a limit for one model in the future
    is a config change, not a code change.
    """
    from backend.core.config import settings

    return TokenBudget(
        redis_client,
        model=model,
        tpm=settings.llm_tpm,
        rpm=settings.llm_rpm,
        tpd=settings.llm_tpd,
        rpd=settings.llm_rpd,
    )


def reserve_or_raise(redis_client, model: str, estimated_tokens: int) -> Reservation:
    """Reserve capacity for `model`, or raise CapacityWaitError.

    The single call site pipeline nodes use before an LLM call.
    """
    budget = get_budget_for_model(redis_client, model)
    if estimated_tokens > budget.tpm:
        raise RequestTooLargeError(estimated_tokens, budget.tpm, model)
    result = budget.reserve(estimated_tokens)
    if not result.granted:
        raise CapacityWaitError(wait_seconds=result.wait_seconds, model=model)
    return result.reservation


# ---------------------------------------------------------------------------
# Per-document capacity-wait state, read by GET /documents/{id}.
#
# This is deliberately NOT a DocumentStatus value: that column is a native
# Postgres enum, and adding a value to it is a schema migration (out of
# scope per this session's hard rules). A capacity wait is transient,
# derived state, held only in Redis — the DB's own status stays whatever it
# was ("pending"/"processing") while a document waits its turn.
# ---------------------------------------------------------------------------

_CAPACITY_WAIT_KEY_PREFIX = "capacity_wait:doc:"


def record_capacity_wait(redis_client, document_id: int, wait_seconds: float) -> None:
    """Note that a document is deferred, and when it is expected to start."""
    estimated_start = time.time() + wait_seconds
    redis_client.set(
        f"{_CAPACITY_WAIT_KEY_PREFIX}{document_id}",
        repr(estimated_start),
        ex=int(wait_seconds) + 300,
    )


def clear_capacity_wait(redis_client, document_id: int) -> None:
    redis_client.delete(f"{_CAPACITY_WAIT_KEY_PREFIX}{document_id}")


def get_capacity_wait_estimated_start(redis_client, document_id: int) -> float | None:
    """The epoch-seconds start estimate for a waiting document, or None."""
    value = redis_client.get(f"{_CAPACITY_WAIT_KEY_PREFIX}{document_id}")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_capacity_wait_estimated_starts(
    redis_client, document_ids: list[int]
) -> dict[int, float]:
    """Batch form of `get_capacity_wait_estimated_start`, one round trip.

    Used by the document list route so a page of N documents costs one
    `MGET`, not N separate `GET`s.
    """
    if not document_ids:
        return {}
    keys = [f"{_CAPACITY_WAIT_KEY_PREFIX}{doc_id}" for doc_id in document_ids]
    values = redis_client.mget(keys)
    result: dict[int, float] = {}
    for doc_id, value in zip(document_ids, values):
        if value is None:
            continue
        try:
            result[doc_id] = float(value)
        except (TypeError, ValueError):
            continue
    return result
