"""Shared retry for real-LLM evaluation scripts (ADR 006).

Free-tier capacity waits are routine, not exceptional. Every evaluation
script that calls a real model goes through `with_capacity_retry`, so a
rate limit is waited out instead of being recorded as a wrong answer or
crashing the run.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic_ai.exceptions import ModelHTTPError

from backend.core.token_budget import CapacityWaitError

T = TypeVar("T")

MAX_CAPACITY_RETRIES = 20
CAPACITY_RETRY_BUFFER_SECONDS = 1.0
CAPACITY_RETRY_MAX_WAIT_SECONDS = 90.0


class CapacityRetriesExhaustedError(RuntimeError):
    """Every retry hit a capacity wait. The run should report the case as
    errored, never as a wrong extraction."""


async def with_capacity_retry(
    coro_fn: Callable[[], Awaitable[T]],
    max_retries: int = MAX_CAPACITY_RETRIES,
) -> T:
    """Retry a call that hits the local Redis token bucket
    (`CapacityWaitError`) or a real HTTP 429, sleeping for as long as the
    failure itself says to wait. Any other error is raised at once.
    """
    for _attempt in range(max_retries):
        try:
            return await coro_fn()
        except CapacityWaitError as exc:
            await asyncio.sleep(_bounded_wait(exc.wait_seconds))
        except ModelHTTPError as exc:
            if exc.status_code != 429:
                raise
            await asyncio.sleep(
                _bounded_wait(exc.retry_after or CAPACITY_RETRY_MAX_WAIT_SECONDS)
            )
    raise CapacityRetriesExhaustedError(f"Exceeded {max_retries} capacity retries")


def _bounded_wait(seconds: float) -> float:
    return min(seconds, CAPACITY_RETRY_MAX_WAIT_SECONDS) + CAPACITY_RETRY_BUFFER_SECONDS
