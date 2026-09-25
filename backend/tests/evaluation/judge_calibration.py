"""Calibration controls for DeepEval's GEval judge on contract free-text fields.

The judge is only trusted if positive controls (faithful rewordings of expected
text) pass consistently, AND negative controls (text with material changes like
notice period dropped) fail consistently. Each judgment runs 3 times; the report
is the mean + spread (max-min), not a single sample.

This module builds the control cases and provides the decision logic.
"""

from dataclasses import dataclass
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


# ---------------------------------------------------------------------------
# GEval Configuration
# ---------------------------------------------------------------------------

def build_termination_clause_judge(
    judge_model: Any, threshold: float = 0.5
) -> Any:
    """Build a DeepEval GEval metric for the termination_clause field.

    Args:
        judge_model: A DeepEvalBaseLLM instance (e.g., LLMClientBasedJudge).
        threshold: The passing score threshold (default 0.5).

    Returns:
        A configured DeepEval GEval metric instance.
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCaseParams

    return GEval(
        name="termination_clause_judge",
        criteria=(
            "Evaluate whether the candidate text faithfully captures the "
            "termination or exit clause from the expected text. "
            "Check for: (1) notice periods, (2) conditions for termination, "
            "(3) named parties, (4) key exit conditions. "
            "Reward faithful rewording. Fail if a material condition is missing "
            "or invented."
        ),
        evaluation_params=[LLMTestCaseParams.EXPECTED_OUTPUT],
        model=judge_model,
        threshold=threshold,
        async_mode=True,
    )


def build_key_obligations_judge(
    judge_model: Any, threshold: float = 0.5
) -> Any:
    """Build a DeepEval GEval metric for the key_obligations field.

    Args:
        judge_model: A DeepEvalBaseLLM instance (e.g., LLMClientBasedJudge).
        threshold: The passing score threshold (default 0.5).

    Returns:
        A configured DeepEval GEval metric instance.
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCaseParams

    return GEval(
        name="key_obligations_judge",
        criteria=(
            "Evaluate whether the candidate list of obligations faithfully "
            "captures the expected obligations from the ground truth. "
            "Check each obligation for: (1) semantic accuracy, (2) completeness "
            "(no material conditions dropped), (3) correct named parties. "
            "Reward faithful rewording and correct paraphrasing. Fail if a "
            "material obligation is missing or invented."
        ),
        evaluation_params=[LLMTestCaseParams.EXPECTED_OUTPUT],
        model=judge_model,
        threshold=threshold,
        async_mode=True,
    )
