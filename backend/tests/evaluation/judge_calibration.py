"""Calibration controls for DeepEval's GEval judge on contract free-text fields.

The judge is only trusted if positive controls (faithful rewordings of expected
text) pass consistently, AND negative controls (text with material changes like
notice period dropped) fail consistently. Each judgment runs 3 times; the report
is the mean + spread (max-min), not a single sample.

This module builds the control cases and provides the decision logic.
"""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class JudgmentRun:
    """Result of a single judge invocation."""
    score: float
    """The judge's score (0.0–1.0)."""


@dataclass
class ControlResult:
    """Result of calibration for one control case."""
    case_id: str
    is_positive: bool
    """True for positive controls (should pass), False for negative."""
    candidate: str
    """The text presented to the judge."""
    expected: str
    """The golden ground truth."""
    scores: list[float]
    """List of scores from 3 judge runs."""
    field_name: str = "unknown"
    """Which scoped field this control is for (termination_clause or
    key_obligations) - defaults to "unknown" for backward compatibility
    with callers that pre-date this field."""

    @property
    def mean_score(self) -> float:
        """Mean of the 3 scores."""
        if not self.scores:
            return 0.0
        return sum(self.scores) / len(self.scores)

    @property
    def spread(self) -> float:
        """Max - Min of the 3 scores (measure of variance)."""
        if not self.scores:
            return 0.0
        return max(self.scores) - min(self.scores)


def calibration_passed(
    controls: list[ControlResult],
    threshold: float = 0.5,
) -> bool:
    """Check if all calibration controls passed.

    For calibration to pass:
    - ALL positive controls must have mean_score >= threshold
    - ALL negative controls must have mean_score < threshold

    Args:
        controls: List of calibration results.
        threshold: The judge's passing score threshold (default 0.5).

    Returns:
        True only if all positives pass AND all negatives fail.
    """
    if not controls:
        # Empty controls list — conservatively say no
        return False

    positives = [c for c in controls if c.is_positive]
    negatives = [c for c in controls if not c.is_positive]

    # All positives must pass
    if positives and not all(c.mean_score >= threshold for c in positives):
        return False

    # All negatives must fail
    if negatives and not all(c.mean_score < threshold for c in negatives):
        return False

    # If we have at least one of each type, or at least one of either type, pass
    return len(controls) > 0


CALIBRATION_CSV_FIELDS = [
    "case_id",
    "field_name",
    "is_positive",
    "candidate",
    "expected",
    "scores",
    "mean_score",
    "spread",
    "human_verdict",
]


def write_calibration_csv(controls: list[ControlResult], path: Path) -> None:
    """Write real calibration outputs to a CSV for manual spot-checking
    later (ADR 008). `human_verdict` is left empty - nothing in the
    calibration decision depends on it being filled in."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CALIBRATION_CSV_FIELDS)
        writer.writeheader()
        for control in controls:
            writer.writerow(
                {
                    "case_id": control.case_id,
                    "field_name": control.field_name,
                    "is_positive": control.is_positive,
                    "candidate": control.candidate,
                    "expected": control.expected,
                    "scores": control.scores,
                    "mean_score": control.mean_score,
                    "spread": control.spread,
                    "human_verdict": "",
                }
            )


# ---------------------------------------------------------------------------
# GEval Configuration
# ---------------------------------------------------------------------------

def build_termination_clause_judge(
    judge_model: Any, threshold: float = 0.5
) -> Any:
    """Build a DeepEval GEval metric for the termination_clause field.

    Uses explicit `evaluation_steps` rather than a bare `criteria` string
    (ADR 008): a bare criteria string makes GEval generate its own steps via
    an internal LLM call at measure time, which is not reproducible run to
    run — the whole point of hand-authoring steps here.

    Args:
        judge_model: A DeepEvalBaseLLM instance (e.g., LLMClientBasedJudge).
        threshold: The passing score threshold (default 0.5).

    Returns:
        A configured DeepEval GEval metric instance.
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import SingleTurnParams

    return GEval(
        name="termination_clause_judge",
        evaluation_steps=[
            "Compare the actual output against the expected output's "
            "termination or exit clause.",
            "Check whether the notice period matches (or is a faithful "
            "rewording of) the expected notice period.",
            "Check whether the conditions for termination match the "
            "expected conditions.",
            "Check whether the named parties match the expected parties.",
            "Reward faithful rewording that preserves all of the above.",
            "Fail the response if any material condition above is missing, "
            "changed, or invented relative to the expected output.",
        ],
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        model=judge_model,
        threshold=threshold,
        async_mode=True,
    )


def build_key_obligations_judge(
    judge_model: Any, threshold: float = 0.5
) -> Any:
    """Build a DeepEval GEval metric for the key_obligations field.

    Uses explicit `evaluation_steps` for the same reproducibility reason as
    `build_termination_clause_judge` above.

    Args:
        judge_model: A DeepEvalBaseLLM instance (e.g., LLMClientBasedJudge).
        threshold: The passing score threshold (default 0.5).

    Returns:
        A configured DeepEval GEval metric instance.
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import SingleTurnParams

    return GEval(
        name="key_obligations_judge",
        evaluation_steps=[
            "Compare the actual output's list of obligations against the "
            "expected output's list of obligations.",
            "Check each expected obligation is present in the actual "
            "output, allowing faithful rewording and paraphrasing.",
            "Check that no material obligation from the expected output is "
            "missing from the actual output.",
            "Check that no obligation in the actual output is invented "
            "(absent from the expected output).",
            "Check that named parties for each obligation match the "
            "expected output.",
            "Fail the response if any material obligation is missing, "
            "changed, or invented relative to the expected output.",
        ],
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        model=judge_model,
        threshold=threshold,
        async_mode=True,
    )
