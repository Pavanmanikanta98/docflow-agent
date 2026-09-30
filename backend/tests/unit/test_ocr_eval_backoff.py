"""ADR 007 — the OCR eval's 429 backoff must respect the server's own
rate-limit signal instead of a fixed schedule (a real free-tier TPM window
takes longer to clear than the original guessed 2.2-35.2s backoff)."""

from pydantic_ai.exceptions import ModelHTTPError

from backend.tests.evaluation.run_ocr_eval import (
    _parse_duration_seconds,
    _rate_limit_wait_seconds,
)


def test_parses_minutes_and_seconds():
    assert _parse_duration_seconds("1m26.4s") == 86.4


def test_parses_milliseconds_only():
    assert _parse_duration_seconds("585ms") == 0.585


def test_parses_seconds_only():
    assert _parse_duration_seconds("26.4s") == 26.4


def test_unparseable_duration_returns_none():
    assert _parse_duration_seconds("not-a-duration") is None


def test_wait_prefers_retry_after_header():
    exc = ModelHTTPError(status_code=429, model_name="m", headers={"retry-after": "12"})
    assert _rate_limit_wait_seconds(exc, fallback=2.2) == 13.0


def test_wait_falls_back_to_groq_reset_headers_when_no_retry_after():
    exc = ModelHTTPError(
        status_code=429,
        model_name="m",
        headers={
            "x-ratelimit-reset-tokens": "1m26.4s",
            "x-ratelimit-reset-requests": "585ms",
        },
    )
    assert _rate_limit_wait_seconds(exc, fallback=2.2) == 87.4


def test_wait_uses_fallback_when_no_headers_at_all():
    exc = ModelHTTPError(status_code=429, model_name="m", headers=None)
    assert _rate_limit_wait_seconds(exc, fallback=2.2) == 2.2


def test_wait_uses_fallback_for_non_429_errors():
    exc = ModelHTTPError(status_code=500, model_name="m", headers={"retry-after": "12"})
    assert _rate_limit_wait_seconds(exc, fallback=2.2) == 2.2
