"""Tests for the metrics timing utilities."""

import time

import pytest

from backend.core.metrics import timed


def test_timed_records_duration() -> None:
    """timed() should record the elapsed time in the metrics dict."""
    metrics: dict[str, float] = {}
    sleep_time = 0.05

    with timed("sleep_test", metrics):
        time.sleep(sleep_time)

    assert "sleep_test" in metrics
    assert metrics["sleep_test"] >= sleep_time
    # Allow some slack for test environment variance
    assert metrics["sleep_test"] < sleep_time + 0.5


def test_timed_with_none_metrics() -> None:
    """timed() should work even when metrics dict is not provided."""
    with timed("test"):
        time.sleep(0.01)

    # Should not raise; we're just checking it completes without error


def test_timed_reraises_exceptions() -> None:
    """timed() should re-raise exceptions, not swallow them."""
    metrics: dict[str, float] = {}

    class CustomError(Exception):
        pass

    with pytest.raises(CustomError):
        with timed("failing_operation", metrics):
            raise CustomError("test error")

    # The metric should still be recorded even though an exception was raised
    assert "failing_operation" in metrics
    assert metrics["failing_operation"] > 0


def test_timed_multiple_timings() -> None:
    """timed() should allow recording multiple timings in the same dict."""
    metrics: dict[str, float] = {}

    with timed("op1", metrics):
        time.sleep(0.01)

    with timed("op2", metrics):
        time.sleep(0.01)

    assert "op1" in metrics
    assert "op2" in metrics
    assert metrics["op1"] > 0
    assert metrics["op2"] > 0
