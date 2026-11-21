#!/usr/bin/env python3
"""
Evaluation runner for docflow-agent.

Runs the golden invoice and contract datasets against a model and writes
structured JSON results with per-field accuracy.

Usage:
    uv run python -m backend.tests.evaluation.run_eval --model openai/gpt-oss-20b

Scoring rules (shared with the pytest suite in this folder):
- Every field of the plugin's extraction schema is scored, except
  `confidence_score`. A field missing from a golden case's `expected` means
  the document does not state it, so the right answer is null.
- A rate limit is retried (`retry.with_capacity_retry`). A case that still
  cannot be extracted is reported under `errored_cases` and left out of
  field accuracy: it measures the API, not the extraction.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.agents.extractor import extract_fields_with_usage
from backend.core.llm import llm_client
from backend.core.metrics import timed
from backend.plugins import get_plugin
from backend.tests.evaluation.conftest import (
    CaseResult,
    FieldResult,
    date_match,
    exact_match_number,
    fuzzy_match,
    list_overlap_score,
    load_golden,
    null_match,
)
from backend.tests.evaluation.retry import with_capacity_retry
from backend.tests.evaluation.run_config import build_run_config
from backend.tests.evaluation.run_stats import usage_summary

RESULTS_DIR = Path(__file__).resolve().parents[3] / "evals" / "results"
UNSCORED_FIELDS = frozenset({"confidence_score"})

NUMBER_FIELDS = frozenset({"total_amount", "subtotal", "tax_amount", "contract_value"})
DATE_FIELDS = frozenset({"invoice_date", "due_date", "effective_date", "expiry_date"})
LIST_FIELDS = frozenset({"line_items", "parties", "key_obligations"})
LIST_OVERLAP_THRESHOLD = 0.6
TEXT_MATCH_THRESHOLD = 0.75


@dataclass
class AggregatedResults:
    """Summary statistics across all scored (non-errored) cases."""

    total_cases: int
    passed_cases: int
    total_fields: int
    passed_fields: int
    field_results: dict[str, dict[str, int]]  # {field_name: {passed, total}}
    wall_clock_seconds: float
    cases: list[CaseResult]
    errored_cases: list[dict[str, str]] = field(default_factory=list)

    def accuracy(self) -> float:
        """Overall field-level accuracy."""
        if self.total_fields == 0:
            return 0.0
        return self.passed_fields / self.total_fields


def scored_fields(document_type: str) -> list[str]:
    """The fields scored for a document type: its whole extraction schema."""
    schema = get_plugin(document_type).extraction_schema
    return [name for name in schema.model_fields if name not in UNSCORED_FIELDS]


async def evaluate_single_case(
    case: dict[str, Any], model: Any, document_type: str
) -> CaseResult:
    """Extract one golden case and score every schema field.

    Extraction errors propagate; a capacity wait is retried first.
    """
    plugin = get_plugin(document_type)
    timing: dict[str, float] = {}

    async def extract_once() -> tuple[Any, Any]:
        with timed("extract", timing):  # times the successful attempt only
            return await extract_fields_with_usage(case["input"], plugin, model)

    fields, usage = await with_capacity_retry(extract_once)
    extraction = fields.model_dump()

    result = CaseResult(
        case_id=case["case_id"],
        description=case.get("description", ""),
        latency_ms=timing["extract"] * 1000,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )
    for field_name in scored_fields(document_type):
        actual = extraction.get(field_name)
        expected = case["expected"].get(field_name)
        result.field_results.append(
            FieldResult(
                field_name=field_name,
                passed=_score_field(field_name, actual, expected),
                actual=actual,
                expected=expected,
                detail=f"actual={actual!r}, expected={expected!r}",
            )
        )
    return result


def _score_field(field_name: str, actual: Any, expected: Any) -> bool:
    """Score one field with the matcher for its type."""
    if not null_match(actual, expected):
        return False
    if actual is None and expected is None:
        return True
    if field_name in NUMBER_FIELDS:
        return exact_match_number(actual, expected)
    if field_name in DATE_FIELDS:
        return date_match(actual, expected)
    if field_name in LIST_FIELDS:
        score = list_overlap_score(actual, expected, threshold=LIST_OVERLAP_THRESHOLD)
        return score >= LIST_OVERLAP_THRESHOLD
    return fuzzy_match(actual, expected, threshold=TEXT_MATCH_THRESHOLD)


async def _evaluate_or_error(
    case: dict[str, Any], model: Any, document_type: str
) -> CaseResult:
    try:
        return await evaluate_single_case(case, model, document_type)
    except Exception as exc:  # noqa: BLE001 — any failure is an errored case
        return CaseResult(
            case_id=case["case_id"],
            description=case.get("description", ""),
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )


async def run_evaluation(
    model: Any,
    invoice_cases: list[dict],
    contract_cases: list[dict],
) -> AggregatedResults:
    """Run every case once and aggregate the scored ones."""
    all_cases = [("invoice", c) for c in invoice_cases] + [
        ("contract", c) for c in contract_cases
    ]
    results: list[CaseResult] = []
    start_time = time.perf_counter()
    for index, (doc_type, case) in enumerate(all_cases, start=1):
        result = await _evaluate_or_error(case, model, doc_type)
        score = f"{result.passed_count}/{result.total_count}"
        status = "ERROR" if result.error else score
        print(f"[{index}/{len(all_cases)}] {case['case_id']}: {status}", flush=True)
        results.append(result)
    return aggregate(results, time.perf_counter() - start_time)


def aggregate(results: list[CaseResult], wall_clock: float) -> AggregatedResults:
    """Sum field checks over cases that were scored; list errored ones."""
    scored = [r for r in results if r.error is None]
    per_field: dict[str, dict[str, int]] = {}
    for result in scored:
        for fr in result.field_results:
            counts = per_field.setdefault(fr.field_name, {"passed": 0, "total": 0})
            counts["total"] += 1
            counts["passed"] += int(fr.passed)
    return AggregatedResults(
        total_cases=len(scored),
        passed_cases=sum(1 for r in scored if r.accuracy == 1.0),
        total_fields=sum(c["total"] for c in per_field.values()),
        passed_fields=sum(c["passed"] for c in per_field.values()),
        field_results=per_field,
        wall_clock_seconds=wall_clock,
        cases=scored,
        errored_cases=[
            {"case_id": r.case_id, "error": r.error} for r in results if r.error
        ],
    )


def format_model_slug(model_name: str) -> str:
    """e.g. "openai/gpt-oss-20b" -> "openai-gpt-oss-20b"."""
    return model_name.replace("/", "-")


def write_results(
    results: AggregatedResults, model_name: str, output_dir: Path
) -> Path:
    """Write results to `<output_dir>/<YYYY-MM-DD>-<model-slug>.json`."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = output_dir / f"{date_str}-{format_model_slug(model_name)}.json"
    data = {
        "model": model_name,
        "date": date_str,
        "run_config": build_run_config(model_name),
        "usage": usage_summary(results.cases, model_name),
        "wall_clock_seconds": results.wall_clock_seconds,
        "total_cases": results.total_cases,
        "passed_cases": results.passed_cases,
        "total_fields": results.total_fields,
        "passed_fields": results.passed_fields,
        "errored_cases": results.errored_cases,
        "field_results": results.field_results,
        "cases": [asdict(case) for case in results.cases],
    }
    filename.write_text(json.dumps(data, indent=2))
    return filename


def print_summary(results: AggregatedResults, model_name: str) -> None:
    """Print a markdown summary table to stdout."""
    print(f"\n# Evaluation Results — {model_name}\n")
    print("| Metric | Value |\n|---|---|")
    print(f"| Model | {model_name} |")
    print(f"| Cases scored | {results.total_cases} |")
    print(f"| Cases errored (not scored) | {len(results.errored_cases)} |")
    print(f"| Cases with 100% accuracy | {results.passed_cases} |")
    print(
        f"| Field-level accuracy | {results.passed_fields}/{results.total_fields} "
        f"({results.accuracy():.1%}) |"
    )
    print(f"| Wall clock time | {results.wall_clock_seconds:.2f}s |")
    usage = usage_summary(results.cases, model_name)
    latency = usage["latency_ms"]
    if latency["p50"] is not None:
        print(f"| Latency p50 / p95 | {latency['p50']:.0f} / {latency['p95']:.0f} ms |")
    print(f"| Cost | {usage['cost_usd']} |")
    print("\n| Field | Passed | Total | Accuracy |\n|---|---|---|---|")
    for name in sorted(results.field_results):
        counts = results.field_results[name]
        acc = counts["passed"] / counts["total"] if counts["total"] else 0.0
        print(f"| {name} | {counts['passed']} | {counts['total']} | {acc:.1%} |")
    for errored in results.errored_cases:
        print(f"\nERRORED {errored['case_id']}: {errored['error']}")


def main() -> None:
    """Run evaluation and write structured results."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", "-m", default="openai/gpt-oss-20b")
    args = parser.parse_args()

    invoice_cases = load_golden("invoices.json")
    contract_cases = load_golden("contracts.json")
    print(f"Loaded {len(invoice_cases)} invoices, {len(contract_cases)} contracts")

    model = llm_client.get_model(model_name=args.model)
    results = asyncio.run(run_evaluation(model, invoice_cases, contract_cases))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = write_results(results, args.model, RESULTS_DIR)
    print(f"Results written to: {output_file}")
    print_summary(results, args.model)


if __name__ == "__main__":
    main()
