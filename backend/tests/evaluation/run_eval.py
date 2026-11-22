#!/usr/bin/env python3
"""
Evaluation runner for docflow-agent.

Runs the golden invoice and contract datasets against a model and writes
structured JSON results with per-field accuracy.

Usage:
    uv run python -m backend.tests.evaluation.run_eval --model openai/gpt-oss-20b
    uv run python -m backend.tests.evaluation.run_eval --slice ci   # CI gate slice

Each case runs `runs_per_case` times (evals/thresholds.toml) unless --runs
is given; the result file reports mean/min/max per field.

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
from backend.tests.evaluation.run_stats import repeat_summary, usage_summary
from backend.tests.evaluation.thresholds import load_thresholds

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


async def run_repeated(
    model: Any,
    invoice_cases: list[dict],
    contract_cases: list[dict],
    runs: int,
) -> list[AggregatedResults]:
    """Extract every case `runs` times; one AggregatedResults per run."""
    results = []
    for run in range(1, runs + 1):
        print(f"--- run {run}/{runs} ---", flush=True)
        results.append(await run_evaluation(model, invoice_cases, contract_cases))
    return results


def select_cases(cases: list[dict], case_ids: list[str] | None) -> list[dict]:
    """Keep only `case_ids` (all cases when None). An unknown id is an
    error, so a typo in the slice cannot silently shrink what is measured."""
    if case_ids is None:
        return cases
    known = {c["case_id"] for c in cases}
    missing = [cid for cid in case_ids if cid not in known]
    if missing:
        raise ValueError(f"Unknown case ids: {', '.join(missing)}")
    wanted = set(case_ids)
    return [c for c in cases if c["case_id"] in wanted]


def write_results(
    runs: list[AggregatedResults],
    model_name: str,
    output_dir: Path,
    label: str | None = None,
) -> Path:
    """Write `<output_dir>/<YYYY-MM-DD>-<model-slug>[-<label>].json`.

    Top-level `total_fields` / `passed_fields` / `field_results` are sums
    over runs; `field_accuracy` and `per_field` give mean/min/max.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    suffix = f"-{label}" if label else ""
    filename = output_dir / f"{date_str}-{format_model_slug(model_name)}{suffix}.json"
    run_dicts = [_run_summary(r) for r in runs]
    all_cases = [(i, c) for i, r in enumerate(runs, start=1) for c in r.cases]
    data = {
        "model": model_name,
        "date": date_str,
        "runs_per_case": len(runs),
        "run_config": build_run_config(model_name),
        "usage": usage_summary([c for _, c in all_cases], model_name),
        **repeat_summary(run_dicts),
        "total_fields": sum(r.total_fields for r in runs),
        "passed_fields": sum(r.passed_fields for r in runs),
        "field_results": _summed_field_results(runs),
        "wall_clock_seconds": sum(r.wall_clock_seconds for r in runs),
        "errored_cases": [
            {"run": i, **e}
            for i, r in enumerate(runs, start=1)
            for e in r.errored_cases
        ],
        "runs": [{"run": i, **d} for i, d in enumerate(run_dicts, start=1)],
        "cases": [{"run": i, **asdict(c)} for i, c in all_cases],
    }
    filename.write_text(json.dumps(data, indent=2))
    return filename


def _run_summary(run: AggregatedResults) -> dict[str, Any]:
    return {
        "total_cases": run.total_cases,
        "passed_cases": run.passed_cases,
        "total_fields": run.total_fields,
        "passed_fields": run.passed_fields,
        "field_results": run.field_results,
        "wall_clock_seconds": run.wall_clock_seconds,
    }


def _summed_field_results(runs: list[AggregatedResults]) -> dict[str, dict[str, int]]:
    summed: dict[str, dict[str, int]] = {}
    for run in runs:
        for name, counts in run.field_results.items():
            target = summed.setdefault(name, {"passed": 0, "total": 0})
            target["passed"] += counts["passed"]
            target["total"] += counts["total"]
    return summed


def print_summary(result_file: Path) -> None:
    """Print a markdown summary of a written result file."""
    data = json.loads(result_file.read_text())
    acc = data["field_accuracy"]
    usage = data["usage"]
    print(f"\n# Evaluation Results — {data['model']} ({data['date']})\n")
    print("| Metric | Value |\n|---|---|")
    print(f"| Runs per case | {data['runs_per_case']} |")
    print(f"| Field checks passed (all runs) | {data['passed_fields']}/"
          f"{data['total_fields']} |")
    if acc["mean"] is not None:
        print(f"| Field accuracy mean (min-max) | {acc['mean']:.1%} "
              f"({acc['min']:.1%}-{acc['max']:.1%}) |")
    print(f"| Cases errored (not scored) | {len(data['errored_cases'])} |")
    latency = usage["latency_ms"]
    if latency["p50"] is not None:
        print(f"| Latency p50 / p95 | {latency['p50']:.0f} / "
              f"{latency['p95']:.0f} ms (n={usage['n']}) |")
    print(f"| Cost | {usage['cost_usd']} |")
    print("\n| Field | Mean | Min | Max |\n|---|---|---|---|")
    for name, f in data["per_field"].items():
        print(f"| {name} | {f['mean']:.1%} | {f['min']:.1%} | {f['max']:.1%} |")
    for errored in data["errored_cases"]:
        print(f"\nERRORED run {errored['run']} {errored['case_id']}: "
              f"{errored['error']}")


def main(argv: list[str] | None = None) -> None:
    """Run evaluation and write structured results."""
    thresholds = load_thresholds()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", "-m", default="openai/gpt-oss-20b")
    parser.add_argument("--runs", type=int, default=thresholds.runs_per_case)
    parser.add_argument(
        "--slice", choices=["ci"], default=None,
        help="Run only the CI slice listed in evals/thresholds.toml.",
    )
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args(argv)

    case_ids = list(thresholds.ci_slice_cases) if args.slice == "ci" else None
    invoices = select_cases(load_golden("invoices.json"), _ids(case_ids, "inv_"))
    contracts = select_cases(load_golden("contracts.json"), _ids(case_ids, "con_"))
    print(f"{len(invoices)} invoices, {len(contracts)} contracts, {args.runs} runs")

    model = llm_client.get_model(model_name=args.model)
    runs = asyncio.run(run_repeated(model, invoices, contracts, args.runs))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_file = write_results(runs, args.model, args.output_dir, label=args.slice)
    print(f"Results written to: {output_file}")
    print_summary(output_file)


def _ids(case_ids: list[str] | None, prefix: str) -> list[str] | None:
    if case_ids is None:
        return None
    return [cid for cid in case_ids if cid.startswith(prefix)]


if __name__ == "__main__":
    main()
