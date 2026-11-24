"""The uploaded file's temporary home: Redis, never Postgres.

Rules (issue #56):
- The file is stored at upload with a time limit (`file_buffer_ttl_seconds`).
- While a document is held for human review the reviewer needs to see it, so
  the file stays, with a fresh time limit.
- Once nobody needs it (the document completed, failed, or the reviewer
  approved or rejected it) it is deleted at once.

Upload, worker and review route all go through here, so the rule lives in one
place.
"""

from typing import Any

from backend.core.config import settings
from backend.models.db import DocumentStatus


def buffer_key(document_id: int) -> str:
    return f"doc_bytes:{document_id}"


def store(redis: Any, document_id: int, file_bytes: bytes) -> None:
    redis.setex(buffer_key(document_id), settings.file_buffer_ttl_seconds, file_bytes)


def release(redis: Any, document_id: int) -> None:
    redis.delete(buffer_key(document_id))


def keep_for_review_or_release(
    redis: Any, document_id: int, status: DocumentStatus
) -> None:
    """After processing: keep the file only for a document awaiting review."""
    if status == DocumentStatus.awaiting_review:
        redis.expire(buffer_key(document_id), settings.file_buffer_ttl_seconds)
    else:
        release(redis, document_id)
