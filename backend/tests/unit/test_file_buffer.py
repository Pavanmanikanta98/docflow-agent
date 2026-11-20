"""Issue #56: the uploaded file stays in Redis while a reviewer needs it, and
is deleted as soon as nobody does. Never stored in Postgres."""

import pytest

from backend.core.file_buffer import (
    buffer_key,
    keep_for_review_or_release,
    release,
    store,
)
from backend.models.db import DocumentStatus


class FakeRedis:
    """Just enough Redis: values and their TTLs."""

    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def setex(self, key: str, ttl: int, value: bytes) -> None:
        self.values[key], self.ttls[key] = value, ttl

    def expire(self, key: str, ttl: int) -> None:
        if key in self.values:
            self.ttls[key] = ttl

    def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.ttls.pop(key, None)


def test_store_sets_a_ttl_from_settings() -> None:
    redis = FakeRedis()
    store(redis, 7, b"%PDF")
    assert redis.values[buffer_key(7)] == b"%PDF"
    assert redis.ttls[buffer_key(7)] > 0


def test_a_document_held_for_review_keeps_its_file_with_a_fresh_ttl() -> None:
    redis = FakeRedis()
    store(redis, 7, b"%PDF")
    redis.ttls[buffer_key(7)] = 5  # nearly expired after a long capacity wait

    keep_for_review_or_release(redis, 7, DocumentStatus.awaiting_review)

    assert buffer_key(7) in redis.values
    assert redis.ttls[buffer_key(7)] > 5


@pytest.mark.parametrize("status", [DocumentStatus.completed, DocumentStatus.failed])
def test_a_document_that_needs_no_review_releases_its_file(
    status: DocumentStatus,
) -> None:
    redis = FakeRedis()
    store(redis, 7, b"%PDF")

    keep_for_review_or_release(redis, 7, status)

    assert buffer_key(7) not in redis.values


def test_release_is_safe_when_the_file_is_already_gone() -> None:
    release(FakeRedis(), 99)  # must not raise
