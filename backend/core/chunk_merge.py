"""ADR 006 — merge per-chunk extraction results into one document result.

Pure function, no I/O: `backend.queue.worker` reads each chunk's stored
extraction_results from Redis and calls this once all chunks are in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.plugins.base import DocumentPlugin


@dataclass
class MergeResult:
    fields: dict[str, Any]
    conflict_reasons: list[str] = field(default_factory=list)
    # field_name -> index of the chunk whose value was kept.
    provenance: dict[str, int] = field(default_factory=dict)


def merge_chunk_results(
    plugin: DocumentPlugin, chunk_results: list[dict[str, Any]]
) -> MergeResult:
    """Combine each chunk's extracted fields per the plugin's merge policy.

    `chunk_results` must be in chunk (page) order. Metadata keys already
    present on a chunk's dict (e.g. a leading underscore) are ignored —
    only the plugin's actual schema fields are merged.
    """
    if not chunk_results:
        return MergeResult(fields={})

    all_fields: set[str] = set()
    for result in chunk_results:
        all_fields.update(k for k in result if not k.startswith("_"))

    merged: dict[str, Any] = {}
    conflicts: list[str] = []
    provenance: dict[str, int] = {}

    for field_name in sorted(all_fields):
        policy = plugin.merge_policy_for(field_name)
        per_chunk = [(i, r.get(field_name)) for i, r in enumerate(chunk_results)]
        non_null = [(i, v) for i, v in per_chunk if v is not None]

        if policy == "concat":
            merged[field_name] = _concat(non_null)
            if non_null:
                provenance[field_name] = non_null[0][0]
            continue

        if not non_null:
            merged[field_name] = None
            continue

        chosen_index, chosen_value = (
            non_null[-1] if policy == "last" else non_null[0]
        )
        merged[field_name] = chosen_value
        provenance[field_name] = chosen_index

        distinct_values = _distinct_hashable_values(v for _, v in non_null)
        if len(distinct_values) > 1:
            conflicts.append(f"chunk_conflict:{field_name}")

    return MergeResult(fields=merged, conflict_reasons=conflicts, provenance=provenance)


def _concat(non_null: list[tuple[int, Any]]) -> Any:
    if not non_null:
        return None
    if isinstance(non_null[0][1], list):
        combined: list[Any] = []
        for _, value in non_null:
            combined.extend(value)
        return combined
    return "\n\n".join(str(value) for _, value in non_null)


def _distinct_hashable_values(values) -> set:
    """Distinct values, tolerating unhashable ones (e.g. a stray list) by
    falling back to their repr — good enough for conflict *detection*."""
    try:
        return set(values)
    except TypeError:
        return {repr(v) for v in values}
