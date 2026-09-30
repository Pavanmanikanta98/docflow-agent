"""Unit tests for judge calibration logic.

Tests verify:
- ControlResult.mean_score computes average of 3 scores
- ControlResult.spread computes max - min
- calibration_passed() correctly identifies pass/fail conditions
"""

import pytest

from backend.tests.evaluation.judge_calibration import ControlResult, calibration_passed


def test_control_result_mean_score() -> None:
    """ControlResult.mean_score computes the average of scores."""
    control = ControlResult(
        case_id="test_1",
        is_positive=True,
        candidate="some text",
        expected="expected text",
        scores=[0.6, 0.7, 0.8],
    )
    assert control.mean_score == pytest.approx(0.7)


def test_control_result_spread() -> None:
    """ControlResult.spread computes max - min."""
    control = ControlResult(
        case_id="test_1",
        is_positive=True,
        candidate="some text",
        expected="expected text",
        scores=[0.6, 0.7, 0.8],
    )
    assert control.spread == pytest.approx(0.2)


def test_control_result_spread_identical_scores() -> None:
    """When all scores are identical, spread is 0.0."""
    control = ControlResult(
        case_id="test_1",
        is_positive=True,
        candidate="some text",
        expected="expected text",
        scores=[0.7, 0.7, 0.7],
    )
    assert control.spread == pytest.approx(0.0)


def test_control_result_mean_score_empty() -> None:
    """When scores list is empty, mean_score is 0.0."""
    control = ControlResult(
        case_id="test_1",
        is_positive=True,
        candidate="some text",
        expected="expected text",
        scores=[],
    )
    assert control.mean_score == 0.0


def test_calibration_passed_empty_controls() -> None:
    """Empty controls list fails calibration (conservative)."""
    result = calibration_passed([])
    assert result is False


def test_calibration_passed_all_positives_pass() -> None:
    """When all positives pass (mean >= threshold), and no negatives, pass."""
    controls = [
        ControlResult(
            case_id="pos_1",
            is_positive=True,
            candidate="reworded",
            expected="original",
            scores=[0.6, 0.7, 0.8],  # mean 0.7 >= 0.5 threshold
        ),
    ]
    result = calibration_passed(controls, threshold=0.5)
    assert result is True


def test_calibration_passed_all_negatives_fail() -> None:
    """When all negatives fail (mean < threshold), and no positives, pass."""
    controls = [
        ControlResult(
            case_id="neg_1",
            is_positive=False,
            candidate="modified with notice dropped",
            expected="original",
            scores=[0.2, 0.3, 0.4],  # mean 0.3 < 0.5 threshold
        ),
    ]
    result = calibration_passed(controls, threshold=0.5)
    assert result is True


def test_calibration_passed_both_pass_and_fail_correctly() -> None:
    """When positives all pass and negatives all fail, pass."""
    controls = [
        ControlResult(
            case_id="pos_1",
            is_positive=True,
            candidate="reworded",
            expected="original",
            scores=[0.6, 0.7, 0.8],  # mean 0.7
        ),
        ControlResult(
            case_id="neg_1",
            is_positive=False,
            candidate="modified",
            expected="original",
            scores=[0.2, 0.3, 0.4],  # mean 0.3
        ),
    ]
    result = calibration_passed(controls, threshold=0.5)
    assert result is True


def test_calibration_failed_positive_below_threshold() -> None:
    """When a positive control's mean < threshold, fail."""
    controls = [
        ControlResult(
            case_id="pos_1",
            is_positive=True,
            candidate="reworded",
            expected="original",
            scores=[0.2, 0.3, 0.4],  # mean 0.3 < 0.5 threshold
        ),
    ]
    result = calibration_passed(controls, threshold=0.5)
    assert result is False


def test_calibration_failed_negative_above_threshold() -> None:
    """When a negative control's mean >= threshold, fail."""
    controls = [
        ControlResult(
            case_id="neg_1",
            is_positive=False,
            candidate="modified",
            expected="original",
            scores=[0.6, 0.7, 0.8],  # mean 0.7 >= 0.5 threshold
        ),
    ]
    result = calibration_passed(controls, threshold=0.5)
    assert result is False


def test_calibration_failed_mixed_results() -> None:
    """When one positive passes but one negative also passes, fail."""
    controls = [
        ControlResult(
            case_id="pos_1",
            is_positive=True,
            candidate="reworded",
            expected="original",
            scores=[0.6, 0.7, 0.8],  # mean 0.7 >= threshold
        ),
        ControlResult(
            case_id="neg_1",
            is_positive=False,
            candidate="modified",
            expected="original",
            scores=[0.6, 0.7, 0.8],  # mean 0.7 >= threshold (SHOULD FAIL)
        ),
    ]
    result = calibration_passed(controls, threshold=0.5)
    assert result is False


def test_calibration_passed_with_higher_threshold() -> None:
    """Threshold can be changed; calibration respects it."""
    controls = [
        ControlResult(
            case_id="pos_1",
            is_positive=True,
            candidate="reworded",
            expected="original",
            scores=[0.6, 0.7, 0.8],  # mean 0.7
        ),
    ]
    result = calibration_passed(controls, threshold=0.75)
    # 0.7 < 0.75, so this should fail
    assert result is False

    result = calibration_passed(controls, threshold=0.6)
    # 0.7 >= 0.6, so this should pass
    assert result is True


def test_calibration_passed_multiple_controls_all_correct() -> None:
    """With multiple controls, all must pass for calibration to pass."""
    controls = [
        ControlResult(
            case_id="pos_1",
            is_positive=True,
            candidate="reworded 1",
            expected="original 1",
            scores=[0.6, 0.7, 0.8],
        ),
        ControlResult(
            case_id="pos_2",
            is_positive=True,
            candidate="reworded 2",
            expected="original 2",
            scores=[0.65, 0.75, 0.85],
        ),
        ControlResult(
            case_id="neg_1",
            is_positive=False,
            candidate="modified 1",
            expected="original 1",
            scores=[0.2, 0.3, 0.4],
        ),
        ControlResult(
            case_id="neg_2",
            is_positive=False,
            candidate="modified 2",
            expected="original 2",
            scores=[0.15, 0.25, 0.35],
        ),
    ]
    result = calibration_passed(controls, threshold=0.5)
    assert result is True


def test_calibration_failed_one_negative_just_below_threshold() -> None:
    """When even one negative is at/above threshold, fail."""
    controls = [
        ControlResult(
            case_id="pos_1",
            is_positive=True,
            candidate="reworded",
            expected="original",
            scores=[0.6, 0.7, 0.8],
        ),
        ControlResult(
            case_id="neg_1",
            is_positive=False,
            candidate="modified",
            expected="original",
            scores=[0.49, 0.5, 0.51],  # mean 0.5 >= threshold
        ),
    ]
    result = calibration_passed(controls, threshold=0.5)
    assert result is False
