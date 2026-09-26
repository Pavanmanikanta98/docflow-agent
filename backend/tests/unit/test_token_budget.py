"""Unit tests for backend.core.token_budget (ADR 006).

Bucket math runs against a REAL Redis instance — the Lua script's atomicity
and TTL behaviour are exactly what a mock would fail to exercise honestly.
Skipped with a clear reason when Redis is unreachable (e.g. a laptop with no
`docker compose up -d` running).
"""

import uuid

import pytest
import redis as redis_lib

from backend.core.token_budget import (
    CapacityWaitError,
    TokenBudget,
    _parse_groq_duration,
    estimate_tokens,
    reserve_or_raise,
)


def _redis_available() -> bool:
    try:
        client = redis_lib.from_url(
            "redis://localhost:6379/15", socket_connect_timeout=1
        )
        client.ping()
        return True
    except redis_lib.exceptions.RedisError:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis is not reachable at redis://localhost:6379/15 (start it with "
    "`docker compose up -d` or `redis-server`)",
)


@pytest.fixture()
def redis_client():
    client = redis_lib.from_url("redis://localhost:6379/15")
    yield client
    client.flushdb()


@pytest.fixture()
def clock():
    """A controllable fake clock so window boundaries are deterministic."""
    state = {"now": 1_000_000.0}

    def now_fn():
        return state["now"]

    now_fn.state = state
    return now_fn


def unique_model() -> str:
    return f"test-model-{uuid.uuid4().hex[:8]}"


def make_budget(redis_client, clock, tpm=1000, rpm=100, tpd=100000, rpd=10000):
    return TokenBudget(
        redis_client,
        model=unique_model(),
        tpm=tpm,
        rpm=rpm,
        tpd=tpd,
        rpd=rpd,
        now_fn=clock,
    )


# ---------------------------------------------------------------------------
# estimate_tokens — pure function, no Redis
# ---------------------------------------------------------------------------

def test_estimate_tokens_includes_completion_budget():
    messages = [{"role": "user", "content": "hello"}]
    small = estimate_tokens(messages, max_completion_tokens=0)
    with_completion = estimate_tokens(messages, max_completion_tokens=500)
    assert with_completion == small + 500


def test_estimate_tokens_grows_with_message_length():
    short = estimate_tokens(
        [{"role": "user", "content": "hi"}], max_completion_tokens=0
    )
    long = estimate_tokens(
        [{"role": "user", "content": "hi " * 200}], max_completion_tokens=0
    )
    assert long > short


# ---------------------------------------------------------------------------
# duration parsing — pure function, no Redis
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [
        ("585ms", 0.585),
        ("7.66s", 7.66),
        ("1m26.4s", 86.4),
        ("2h", 7200.0),
        ("0s", 0.0),
        ("", 0.0),
        ("garbage", 0.0),
    ],
)
def test_parse_groq_duration(value, expected):
    assert _parse_groq_duration(value) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# reserve / settle / refill — real Redis
# ---------------------------------------------------------------------------

@requires_redis
def test_reserve_grants_within_limits(redis_client, clock):
    budget = make_budget(redis_client, clock, tpm=1000, rpm=10, tpd=5000, rpd=100)
    result = budget.reserve(estimated_tokens=100)
    assert result.granted is True
    assert result.wait_seconds == 0.0
    assert result.reservation is not None


@requires_redis
def test_reserve_defers_when_tpm_exceeded(redis_client, clock):
    budget = make_budget(redis_client, clock)
    first = budget.reserve(estimated_tokens=900)
    assert first.granted is True

    second = budget.reserve(estimated_tokens=200)
    assert second.granted is False
    assert second.wait_seconds > 0
    assert second.reservation is None


@requires_redis
def test_reserve_defers_when_rpm_exceeded(redis_client, clock):
    budget = make_budget(redis_client, clock, tpm=100000, rpm=2, tpd=1000000, rpd=10000)
    assert budget.reserve(estimated_tokens=1).granted is True
    assert budget.reserve(estimated_tokens=1).granted is True
    third = budget.reserve(estimated_tokens=1)
    assert third.granted is False


@requires_redis
def test_reserve_defers_when_daily_cap_exceeded(redis_client, clock):
    budget = make_budget(redis_client, clock, tpm=100000, rpm=1000, tpd=500, rpd=10000)
    assert budget.reserve(estimated_tokens=400).granted is True
    second = budget.reserve(estimated_tokens=200)
    assert second.granted is False
    # Daily cap wait should span (most of) the rest of the day, not a minute.
    assert second.wait_seconds > 60


@requires_redis
def test_window_refills_after_it_elapses(redis_client, clock):
    budget = make_budget(redis_client, clock)
    assert budget.reserve(estimated_tokens=900).granted is True
    assert budget.reserve(estimated_tokens=200).granted is False

    clock.state["now"] += 61  # advance past the minute window
    refilled = budget.reserve(estimated_tokens=200)
    assert refilled.granted is True


@requires_redis
def test_settle_reduces_usage_when_actual_is_lower_than_estimate(redis_client, clock):
    budget = make_budget(redis_client, clock)
    first = budget.reserve(estimated_tokens=900)
    assert first.granted is True

    # Estimate was generous; actual usage was much lower.
    budget.settle(first.reservation, actual_tokens=100)

    # The freed-up headroom should now allow a request that would otherwise
    # have been deferred.
    second = budget.reserve(estimated_tokens=800)
    assert second.granted is True


@requires_redis
def test_settle_increases_usage_when_actual_exceeds_estimate(redis_client, clock):
    budget = make_budget(redis_client, clock)
    first = budget.reserve(estimated_tokens=100)
    assert first.granted is True
    budget.settle(first.reservation, actual_tokens=950)

    second = budget.reserve(estimated_tokens=100)
    assert second.granted is False


# ---------------------------------------------------------------------------
# sync_from_headers — real Redis
# ---------------------------------------------------------------------------

@requires_redis
def test_sync_from_headers_corrects_tracked_usage(redis_client, clock):
    budget = make_budget(redis_client, clock, tpm=8000, rpm=30, tpd=200000, rpd=1000)
    # Our own tracking believes we've used nothing yet, but Groq's response
    # says we're already down to 100 tokens remaining this minute.
    budget.sync_from_headers(
        {
            "x-ratelimit-limit-tokens": "8000",
            "x-ratelimit-remaining-tokens": "100",
            "x-ratelimit-reset-tokens": "45.0s",
            "x-ratelimit-limit-requests": "30",
            "x-ratelimit-remaining-requests": "29",
            "x-ratelimit-reset-requests": "45.0s",
        }
    )
    result = budget.reserve(estimated_tokens=500)
    assert result.granted is False


@requires_redis
def test_sync_from_headers_is_case_insensitive(redis_client, clock):
    budget = make_budget(redis_client, clock, tpm=8000, rpm=30, tpd=200000, rpd=1000)
    budget.sync_from_headers(
        {
            "X-RateLimit-Limit-Tokens": "8000",
            "X-RateLimit-Remaining-Tokens": "50",
            "X-RateLimit-Reset-Tokens": "10s",
        }
    )
    result = budget.reserve(estimated_tokens=100)
    assert result.granted is False


# ---------------------------------------------------------------------------
# cooldown
# ---------------------------------------------------------------------------

@requires_redis
def test_cooldown_blocks_every_reservation_until_it_expires(redis_client, clock):
    budget = make_budget(
        redis_client, clock, tpm=100000, rpm=1000, tpd=1000000, rpd=100000
    )
    budget.set_cooldown(30)
    result = budget.reserve(estimated_tokens=1)
    assert result.granted is False
    assert result.wait_seconds == pytest.approx(30, abs=1)


@requires_redis
def test_cooldown_is_shared_across_models(redis_client, clock):
    a = make_budget(redis_client, clock, tpm=100000, rpm=1000, tpd=1000000, rpd=100000)
    b = make_budget(redis_client, clock, tpm=100000, rpm=1000, tpd=1000000, rpd=100000)
    a.set_cooldown(30)
    assert b.reserve(estimated_tokens=1).granted is False


@requires_redis
def test_cooldown_from_retry_after_header(redis_client, clock):
    budget = make_budget(
        redis_client, clock, tpm=100000, rpm=1000, tpd=1000000, rpd=100000
    )
    budget.set_cooldown_from_retry_after({"retry-after": "12"})
    result = budget.reserve(estimated_tokens=1)
    assert result.granted is False
    assert result.wait_seconds == pytest.approx(12, abs=1)


@requires_redis
def test_reserve_or_raise_raises_capacity_wait_error(redis_client, clock, monkeypatch):
    model = unique_model()
    monkeypatch.setattr("backend.core.config.settings.llm_tpm", 100)
    monkeypatch.setattr("backend.core.config.settings.llm_rpm", 1000)
    monkeypatch.setattr("backend.core.config.settings.llm_tpd", 100000)
    monkeypatch.setattr("backend.core.config.settings.llm_rpd", 10000)

    reserve_or_raise(redis_client, model, estimated_tokens=50)
    with pytest.raises(CapacityWaitError) as exc_info:
        reserve_or_raise(redis_client, model, estimated_tokens=100)
    assert exc_info.value.model == model
    assert exc_info.value.wait_seconds > 0
