"""ADR 006 — Redis-held state for a document being processed in chunks.

Not a DB schema change: the chunk plan, each chunk's text, and each
chunk's extraction result are scratch state a chunked document needs while
it is (possibly slowly, across many deferred jobs) being assembled —
nothing here outlives the document's processing. A 2-day TTL is generous
enough to survive even a TPD-bound wait until tomorrow's reset.
"""

from __future__ import annotations

import json
from typing import Any

_TTL_SECONDS = 2 * 24 * 60 * 60


def _meta_key(document_id: int) -> str:
    return f"chunk_state:{document_id}:meta"


def _chunk_key(document_id: int, chunk_index: int) -> str:
    return f"chunk_state:{document_id}:chunk:{chunk_index}"


def start_chunked_document(
    redis_client, document_id: int, chunk_texts: list[str], full_raw_text: str
) -> None:
    """Record the chunk plan. Call once, before enqueueing chunk 0."""
    meta = {"total_chunks": len(chunk_texts), "full_raw_text": full_raw_text}
    redis_client.set(_meta_key(document_id), json.dumps(meta), ex=_TTL_SECONDS)
    for index, text in enumerate(chunk_texts):
        redis_client.set(
            _chunk_key(document_id, index),
            json.dumps({"text": text}),
            ex=_TTL_SECONDS,
        )


def get_total_chunks(redis_client, document_id: int) -> int | None:
    raw = redis_client.get(_meta_key(document_id))
    if raw is None:
        return None
    return json.loads(raw)["total_chunks"]


def get_full_raw_text(redis_client, document_id: int) -> str:
    raw = redis_client.get(_meta_key(document_id))
    if raw is None:
        return ""
    return json.loads(raw).get("full_raw_text", "")


def get_chunk_text(redis_client, document_id: int, chunk_index: int) -> str:
    raw = redis_client.get(_chunk_key(document_id, chunk_index))
    if raw is None:
        return ""
    return json.loads(raw).get("text", "")


def store_chunk_result(
    redis_client,
    document_id: int,
    chunk_index: int,
    extraction_results: dict[str, Any],
) -> None:
    key = _chunk_key(document_id, chunk_index)
    existing = redis_client.get(key)
    data = json.loads(existing) if existing else {}
    data["result"] = extraction_results
    redis_client.set(key, json.dumps(data), ex=_TTL_SECONDS)


def get_all_chunk_results(
    redis_client, document_id: int, total_chunks: int
) -> list[dict[str, Any]]:
    results = []
    for index in range(total_chunks):
        raw = redis_client.get(_chunk_key(document_id, index))
        data = json.loads(raw) if raw else {}
        results.append(data.get("result", {}))
    return results


def clear_chunk_state(redis_client, document_id: int, total_chunks: int) -> None:
    keys = [_meta_key(document_id)] + [
        _chunk_key(document_id, i) for i in range(total_chunks)
    ]
    redis_client.delete(*keys)
