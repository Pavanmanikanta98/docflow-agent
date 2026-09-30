"""Timing utilities for measuring pipeline performance."""

import time
from contextlib import contextmanager
from typing import Generator


@contextmanager
def timed(
    name: str, metrics: dict[str, float] | None = None
) -> Generator[None, None, None]:
    """
    Context manager to record the duration of a code block.

    Stores the elapsed time in the metrics dict under the given name.
    Re-raises any exception raised inside the with block.

    Args:
        name: Key to store the duration under (e.g. "parse", "extract").
        metrics: Dictionary to store results in. If None, creates a new dict.

    Yields:
        None

    Example:
        >>> metrics = {}
        >>> with timed("my_function", metrics):
        ...     time.sleep(0.1)
        >>> 0.09 < metrics["my_function"] < 0.15
        True
    """
    if metrics is None:
        metrics = {}

    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        metrics[name] = elapsed
