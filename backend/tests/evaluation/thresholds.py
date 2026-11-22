"""Loads the preregistered evaluation thresholds (`evals/thresholds.toml`,
issue #41). TOML via the stdlib `tomllib`, so no new dependency."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

THRESHOLDS_PATH = Path(__file__).resolve().parents[3] / "evals" / "thresholds.toml"


@dataclass(frozen=True)
class Thresholds:
    runs_per_case: int
    field_accuracy_min: float
    grader_agreement_min: float
    max_errored_cases: int
    ci_slice_cases: tuple[str, ...]
    ci_runs_per_case: int


def load_thresholds(path: Path = THRESHOLDS_PATH) -> Thresholds:
    """Read the thresholds file. A missing key is an error, never a default:
    a gate with a silently invented bar is worse than no gate."""
    with path.open("rb") as f:
        data = tomllib.load(f)
    ci = data["ci_slice"]
    return Thresholds(
        runs_per_case=int(data["runs_per_case"]),
        field_accuracy_min=float(data["field_accuracy_min"]),
        grader_agreement_min=float(data["grader_agreement_min"]),
        max_errored_cases=int(data["max_errored_cases"]),
        ci_slice_cases=tuple(ci["cases"]),
        ci_runs_per_case=int(ci["runs_per_case"]),
    )
