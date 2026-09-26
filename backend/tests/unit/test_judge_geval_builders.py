"""ADR 008 — the GEval judges must use hand-authored evaluation_steps, not a
bare criteria string (a bare criteria string makes GEval generate its own
steps via an internal LLM call at measure time, which defeats the point of
a reproducible, calibrated judge)."""

from backend.core.deepeval_judge import LLMClientBasedJudge
from backend.tests.evaluation.judge_calibration import (
    build_key_obligations_judge,
    build_termination_clause_judge,
)


def _fake_judge():
    return LLMClientBasedJudge(model_name="openai/gpt-oss-120b")


def test_termination_clause_judge_uses_evaluation_steps_not_criteria():
    metric = build_termination_clause_judge(_fake_judge())
    assert metric.evaluation_steps
    assert metric.criteria is None


def test_key_obligations_judge_uses_evaluation_steps_not_criteria():
    metric = build_key_obligations_judge(_fake_judge())
    assert metric.evaluation_steps
    assert metric.criteria is None


def test_termination_clause_judge_sees_both_actual_and_expected_output():
    from deepeval.test_case import SingleTurnParams

    metric = build_termination_clause_judge(_fake_judge())
    assert SingleTurnParams.ACTUAL_OUTPUT in metric.evaluation_params
    assert SingleTurnParams.EXPECTED_OUTPUT in metric.evaluation_params


def test_key_obligations_judge_sees_both_actual_and_expected_output():
    from deepeval.test_case import SingleTurnParams

    metric = build_key_obligations_judge(_fake_judge())
    assert SingleTurnParams.ACTUAL_OUTPUT in metric.evaluation_params
    assert SingleTurnParams.EXPECTED_OUTPUT in metric.evaluation_params


def test_judges_use_the_configured_threshold():
    metric = build_termination_clause_judge(_fake_judge(), threshold=0.7)
    assert metric.threshold == 0.7
