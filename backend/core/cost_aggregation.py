"""ADR 006 — pure aggregation of measured token usage, for scripts/cost_report.py.

Expected input shape (one evals/results/*.json file may or may not have
this — only files with it contribute to the cost report):

    {"cases": [
        {"document_type": "invoice", "input_tokens": 450, "output_tokens": 80},
        ...
    ]}

This is the schema `backend/tests/evaluation/run_eval.py` is expected to
emit once its per-case token instrumentation lands (SPRINT.md's V1-7 marks
this "not started" as of 18 Sep 2026) — until then, no file matches it, and
`load_cases_from_result` correctly returns [] rather than guessing at a
different shape.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenUsageCase:
    document_type: str
    input_tokens: int
    output_tokens: int


def load_cases_from_result(data: dict) -> list[TokenUsageCase]:
    """Extract measured cases from one parsed results file, or [] if it
    does not follow the "cases" convention (e.g. the load-test results,
    which measure wait times, not token usage)."""
    cases = data.get("cases")
    if not isinstance(cases, list):
        return []

    extracted: list[TokenUsageCase] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        document_type = case.get("document_type")
        input_tokens = case.get("input_tokens")
        output_tokens = case.get("output_tokens")
        if document_type is None or input_tokens is None or output_tokens is None:
            continue
        extracted.append(
            TokenUsageCase(
                document_type=document_type,
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
            )
        )
    return extracted


@dataclass(frozen=True)
class TokenStats:
    count: int
    median_input: float
    median_output: float
    p95_input: float
    p95_output: float


def _percentile(data: list[int], pct: float) -> float:
    ordered = sorted(data)
    index = max(0, min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1))))
    return float(ordered[index])


def aggregate_by_document_type(cases: list[TokenUsageCase]) -> dict[str, TokenStats]:
    """Group measured cases by document type and summarize their token
    counts. A document type with no cases simply does not appear in the
    result — the caller decides how to report that absence."""
    by_type: dict[str, list[TokenUsageCase]] = {}
    for case in cases:
        by_type.setdefault(case.document_type, []).append(case)

    stats: dict[str, TokenStats] = {}
    for document_type, group in by_type.items():
        inputs = [c.input_tokens for c in group]
        outputs = [c.output_tokens for c in group]
        stats[document_type] = TokenStats(
            count=len(group),
            median_input=statistics.median(inputs),
            median_output=statistics.median(outputs),
            p95_input=_percentile(inputs, 95),
            p95_output=_percentile(outputs, 95),
        )
    return stats
