"""Evaluation gate (issue #41): judge a result file against the
preregistered thresholds in `evals/thresholds.toml`.

Usage:
    uv run python -m backend.tests.evaluation.check_gate evals/results/<file>.json
    ... check_gate <file>.json --agreement evals/results/<date>-grader-agreement.json

Exit code 0 = gate passed, 1 = gate failed (each failed rule is printed).
When GITHUB_STEP_SUMMARY is set (GitHub Actions), the verdict is also
written to the job summary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from backend.tests.evaluation.thresholds import (
    THRESHOLDS_PATH,
    Thresholds,
    load_thresholds,
)


def evaluate_gate(result: dict[str, Any], thresholds: Thresholds) -> list[str]:
    """Return one message per failed rule; an empty list means the gate passed."""
    failures = []
    errored = result.get("errored_cases", [])
    if len(errored) > thresholds.max_errored_cases:
        ids = ", ".join(f"{e['case_id']} (run {e.get('run', 1)})" for e in errored)
        failures.append(
            f"{len(errored)} errored case(s), allowed {thresholds.max_errored_cases}:"
            f" {ids}"
        )

    mean = result["field_accuracy"]["mean"]
    if mean is None or mean < thresholds.field_accuracy_min:
        shown = "none measured" if mean is None else f"{mean:.3f}"
        failures.append(
            f"field accuracy {shown} (mean of runs) is below field_accuracy_min "
            f"{thresholds.field_accuracy_min}; fields below the bar: "
            f"{_fields_below(result, thresholds.field_accuracy_min)}"
        )

    agreement = result.get("grader_agreement")
    if agreement is not None and agreement < thresholds.grader_agreement_min:
        failures.append(
            f"grader agreement {agreement:.3f} is below grader_agreement_min "
            f"{thresholds.grader_agreement_min}"
        )
    return failures


def _fields_below(result: dict[str, Any], bar: float) -> str:
    below = [
        f"{name} ({f['mean']:.2f})"
        for name, f in result.get("per_field", {}).items()
        if f["mean"] is not None and f["mean"] < bar
    ]
    return ", ".join(below) or "none"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluation gate")
    parser.add_argument("result_file", type=Path)
    parser.add_argument("--thresholds", type=Path, default=THRESHOLDS_PATH)
    parser.add_argument(
        "--agreement", type=Path, default=None,
        help="A grader-agreement report (grader_agreement.py report) to enforce.",
    )
    args = parser.parse_args(argv)

    result = json.loads(args.result_file.read_text())
    if args.agreement is not None:
        report = json.loads(args.agreement.read_text())
        result["grader_agreement"] = report["agreement"]
    failures = evaluate_gate(result, load_thresholds(args.thresholds))
    verdict = _verdict(result, failures)
    print(verdict)
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_path, "a") as f:
            f.write(verdict + "\n")
    return 1 if failures else 0


def _verdict(result: dict[str, Any], failures: list[str]) -> str:
    acc = result["field_accuracy"]
    head = "## Eval gate: " + ("FAILED" if failures else "passed")
    if acc["mean"] is None:
        spread = "no field checks measured"
    else:
        spread = (
            f"field accuracy mean {acc['mean']:.1%} "
            f"(min {acc['min']:.1%}, max {acc['max']:.1%}) over "
            f"{result.get('runs_per_case', 1)} run(s), model {result.get('model')}"
        )
    lines = [head, "", spread] + [f"- {f}" for f in failures]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
