"""Latency, token and cost summaries for an evaluation run (issue #40).

Cost is computed from `backend.core.pricing`, the same price table the
rest of the repo uses, and says "not measured" when a model has no price
rather than guessing one.
"""

from __future__ import annotations

import math
from statistics import fmean
from typing import Any

from backend.core.pricing import PRICING_CHECKED_DATE, get_pricing
from backend.tests.evaluation.conftest import CaseResult

DOCUMENTS_PER_COST_UNIT = 1000


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile (the same method as numpy's default)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * q / 100
    low, high = math.floor(rank), math.ceil(rank)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def usage_summary(cases: list[CaseResult], model_name: str) -> dict[str, Any]:
    """p50/p95 latency, mean tokens and cost per document over cases that
    have usage recorded."""
    measured = [c for c in cases if c.input_tokens is not None]
    latencies = [c.latency_ms for c in measured if c.latency_ms is not None]
    inputs = [c.input_tokens or 0 for c in measured]
    outputs = [c.output_tokens or 0 for c in measured]
    return {
        "n": len(measured),
        "latency_ms": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
        },
        "tokens_per_document": {
            "input_mean": fmean(inputs) if inputs else None,
            "output_mean": fmean(outputs) if outputs else None,
        },
        "cost_usd": _cost_summary(inputs, outputs, model_name),
    }


def _cost_summary(
    inputs: list[int], outputs: list[int], model_name: str
) -> dict[str, Any] | str:
    try:
        pricing = get_pricing(model_name)
    except KeyError:
        return f"not measured: no price for {model_name}"
    if not inputs:
        return "not measured: no case recorded token usage"
    per_doc = [pricing.cost(i, o) for i, o in zip(inputs, outputs, strict=True)]
    mean = fmean(per_doc)
    return {
        "per_document_mean": mean,
        "per_1000_documents": mean * DOCUMENTS_PER_COST_UNIT,
        "pricing_checked": PRICING_CHECKED_DATE,
    }


def repeat_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean/min/max field accuracy across repeated runs of the same cases,
    overall and per field. Each run is a dict with `passed_fields`,
    `total_fields` and `field_results` ({field: {passed, total}})."""
    overall = [
        r["passed_fields"] / r["total_fields"] for r in runs if r["total_fields"]
    ]
    per_field_values: dict[str, list[float]] = {}
    per_field_counts: dict[str, dict[str, int]] = {}
    for run in runs:
        for name, counts in run["field_results"].items():
            if counts["total"]:
                per_field_values.setdefault(name, []).append(
                    counts["passed"] / counts["total"]
                )
            summed = per_field_counts.setdefault(name, {"passed": 0, "total": 0})
            summed["passed"] += counts["passed"]
            summed["total"] += counts["total"]
    return {
        "field_accuracy": _spread(overall),
        "per_field": {
            name: {**_spread(values), **per_field_counts[name]}
            for name, values in sorted(per_field_values.items())
        },
    }


def _spread(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "min": None, "max": None}
    return {"mean": fmean(values), "min": min(values), "max": max(values)}
