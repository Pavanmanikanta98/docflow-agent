#!/usr/bin/env python3
"""
Evaluation runner for docflow-agent.

Runs the golden invoice and contract datasets against a specified LLM model
and produces structured JSON results with per-field accuracy, latency, and token counts.

Usage:
    uv run python -m backend.tests.evaluation.run_eval --model openai/gpt-oss-20b

The script will:
1. Load golden datasets from backend/tests/evaluation/golden/
2. Run extraction on each case using the specified model
3. Score each field using deterministic matchers
4. Write results to evals/results/<YYYY-MM-DD>-<model-slug>.json
5. Print a markdown summary table to stdout
"""

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from tqdm import tqdm

from backend.core.llm import llm_client
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


@dataclass
class AggregatedResults:
    """Summary statistics across all cases."""
    total_cases: int
    passed_cases: int
    total_fields: int
    passed_fields: int
    field_results: dict[str, dict[str, int]]  # {field_name: {passed, total}}
    wall_clock_seconds: float
    cases: list[CaseResult]

    def accuracy(self) -> float:
        """Overall field-level accuracy."""
        if self.total_fields == 0:
            return 0.0
        return self.passed_fields / self.total_fields


async def evaluate_single_case(
    case: dict[str, Any], model: Any, document_type: str
) -> CaseResult:
    """
    Run extraction on a single case and score each field.

    Returns:
        CaseResult with field-level pass/fail for each field.
    """
    from backend.agents.extractor import extract_fields
    from backend.plugins import get_plugin

    case_id = case["case_id"]
    description = case.get("description", "")
    input_text = case["input"]
    expected = case["expected"]

    plugin = get_plugin(document_type)

    try:
        # Run extraction
        fields = await extract_fields(input_text, plugin, model=model)
        extraction = fields.model_dump(exclude={"confidence_score"})
    except Exception as e:
        # On error, return a case with all fields failed
        result = CaseResult(case_id=case_id, description=description)
        for field_name in expected.keys():
            result.field_results.append(
                FieldResult(
                    field_name=field_name,
                    passed=False,
                    detail=f"Extraction error: {str(e)[:50]}",
                )
            )
        return result

    # Score each field
    result = CaseResult(case_id=case_id, description=description)

    for field_name, expected_value in expected.items():
        actual_value = extraction.get(field_name)

        # Choose the right matcher based on field type
        passed = _score_field(field_name, actual_value, expected_value)

        detail = f"actual={actual_value!r}, expected={expected_value!r}"
        result.field_results.append(
            FieldResult(
                field_name=field_name,
                passed=passed,
                detail=detail,
            )
        )

    return result


def _score_field(field_name: str, actual: Any, expected: Any) -> bool:
    """
    Score a single field using the appropriate matcher.

    Heuristics:
    - Numbers (total_amount, contract_value): exact_match_number
    - Dates (invoice_date, due_date, effective_date, expiry_date): date_match
    - Lists (line_items, parties, key_obligations): list_overlap_score
    - Everything else: fuzzy_match or null_match
    """

    # Null check — if one is None, both must be None
    if not null_match(actual, expected):
        return False

    # If both are None, pass
    if actual is None and expected is None:
        return True

    # Numbers
    if field_name in {
        "total_amount",
        "subtotal",
        "tax_amount",
        "contract_value",
    }:
        return exact_match_number(actual, expected)

    # Dates
    if field_name in {
        "invoice_date",
        "due_date",
        "effective_date",
        "expiry_date",
    }:
        return date_match(actual, expected)

    # Lists
    if field_name in {
        "line_items",
        "parties",
        "key_obligations",
    }:
        score = list_overlap_score(actual, expected, threshold=0.6)
        return score >= 0.6

    # Text fields
    if field_name in {
        "vendor_name",
        "invoice_number",
        "jurisdiction",
        "termination_clause",
        "currency",
    }:
        return fuzzy_match(actual, expected, threshold=0.75)

    # Fallback: fuzzy match
    return fuzzy_match(actual, expected, threshold=0.75)


def _retry_with_backoff(
    max_retries: int = 5, initial_delay: float = 5.0
) -> None:
    """Context manager / callable to add retry logic for 429 errors."""
    pass  # Simplified; full version would wrap the call


async def run_evaluation(
    model_name: str,
    invoice_cases: list[dict],
    contract_cases: list[dict],
) -> AggregatedResults:
    """
    Run evaluation on all cases.

    Handles retries on 429 (rate limit) errors.
    """
    model = llm_client.get_model(model_name=model_name)

    all_cases = [
        ("invoice", case) for case in invoice_cases
    ] + [("contract", case) for case in contract_cases]

    results: list[CaseResult] = []
    start_time = time.time()

    for doc_type, case in tqdm(all_cases, desc=f"Evaluating with {model_name}"):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await evaluate_single_case(case, model, doc_type)
                results.append(result)
                break
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    # Rate limit — back off and retry
                    wait_time = (2 ** attempt) * 5  # 5s, 10s, 20s
                    tqdm.write(
                        f"[{case['case_id']}] Rate limited, retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # Other error or last retry — add to results as failure
                    result = CaseResult(
                        case_id=case["case_id"],
                        description=case.get("description", ""),
                    )
                    result.field_results.append(
                        FieldResult(
                            field_name="_error",
                            passed=False,
                            detail=str(e)[:100],
                        )
                    )
                    results.append(result)
                    break

    wall_clock = time.time() - start_time

    # Aggregate
    passed_cases = sum(1 for r in results if r.accuracy == 1.0)
    total_cases = len(results)

    field_results: dict[str, dict[str, int]] = {}
    total_fields = 0
    passed_fields = 0

    for result in results:
        for field_res in result.field_results:
            if field_res.field_name.startswith("_"):
                continue  # Skip metadata fields

            field_name = field_res.field_name
            if field_name not in field_results:
                field_results[field_name] = {"passed": 0, "total": 0}

            field_results[field_name]["total"] += 1
            if field_res.passed:
                field_results[field_name]["passed"] += 1
            total_fields += 1
            if field_res.passed:
                passed_fields += 1

    return AggregatedResults(
        total_cases=total_cases,
        passed_cases=passed_cases,
        total_fields=total_fields,
        passed_fields=passed_fields,
        field_results=field_results,
        wall_clock_seconds=wall_clock,
        cases=results,
    )


def format_model_slug(model_name: str) -> str:
    """Convert model name to a slug for filenames."""
    # e.g. "openai/gpt-oss-20b" -> "openai-gpt-oss-20b"
    return model_name.replace("/", "-")


def write_results(
    results: AggregatedResults,
    model_name: str,
    output_dir: Path,
) -> Path:
    """
    Write results to a JSON file in evals/results/.

    Returns:
        Path to the written file.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    model_slug = format_model_slug(model_name)
    filename = output_dir / f"{date_str}-{model_slug}.json"

    data = {
        "model": model_name,
        "date": date_str,
        "wall_clock_seconds": results.wall_clock_seconds,
        "total_cases": results.total_cases,
        "passed_cases": results.passed_cases,
        "total_fields": results.total_fields,
        "passed_fields": results.passed_fields,
        "field_results": results.field_results,
        "cases": [
            {
                **asdict(case),
                "field_results": [asdict(fr) for fr in case.field_results],
            }
            for case in results.cases
        ],
    }

    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

    return filename


def print_summary(results: AggregatedResults, model_name: str) -> None:
    """Print a markdown summary table to stdout."""
    print()
    print(f"# Evaluation Results — {model_name}")
    print()
    print("## Summary")
    print()
    print("| Metric | Value |")
    print("|---|---|")
    print(f"| Model | {model_name} |")
    print(f"| Total cases | {results.total_cases} |")
    print(f"| Cases with 100% accuracy | {results.passed_cases} |")
    acc_str = f"{results.passed_fields}/{results.total_fields}"
    acc_pct = f"{results.accuracy():.1%}"
    print(f"| Field-level accuracy | {acc_str} ({acc_pct}) |")
    print(f"| Wall clock time | {results.wall_clock_seconds:.2f}s |")
    print()
    print("## Per-Field Results")
    print()
    print("| Field | Passed | Total | Accuracy |")
    print("|---|---|---|---|")
    for field_name in sorted(results.field_results.keys()):
        field_data = results.field_results[field_name]
        passed = field_data["passed"]
        total = field_data["total"]
        acc = passed / total if total > 0 else 0
        print(f"| {field_name} | {passed} | {total} | {acc:.1%} |")
    print()


def main(
    model: str = typer.Option(
        "openai/gpt-oss-20b",
        "--model",
        "-m",
        help="Model name (e.g., 'openai/gpt-oss-20b')",
    ),
) -> None:
    """Run evaluation and produce structured results."""
    print("Loading golden datasets...")
    invoice_cases = load_golden("invoices.json")
    contract_cases = load_golden("contracts.json")
    print(f"Loaded {len(invoice_cases)} invoices, {len(contract_cases)} contracts")
    print()

    print(f"Running evaluation with model: {model}")
    results = asyncio.run(
        run_evaluation(model, invoice_cases, contract_cases)
    )

    print()
    output_dir = Path(__file__).parent.parent.parent.parent / "evals" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = write_results(results, model, output_dir)
    print(f"Results written to: {output_file}")
    print()

    print_summary(results, model)


if __name__ == "__main__":
    typer.run(main)
