"""Issue #41: preregistered thresholds, repeated runs with spread, and a
gate that fails when a field breaks. No real LLM calls."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from backend.tests.evaluation.check_gate import evaluate_gate, main
from backend.tests.evaluation.conftest import load_golden
from backend.tests.evaluation.run_eval import (
    run_repeated,
    select_cases,
    write_results,
)
from backend.tests.evaluation.run_stats import repeat_summary
from backend.tests.evaluation.thresholds import Thresholds, load_thresholds

CASE: dict[str, Any] = {
    "case_id": "inv_gate",
    "description": "",
    "input": "INVOICE 7\nFrom: Acme Corp\nTotal: $500.00 USD",
    "expected": {
        "vendor_name": "Acme Corp",
        "invoice_number": "7",
        "total_amount": 500.0,
        "currency": "USD",
    },
}
GOOD = {"vendor_name": "Acme Corp", "invoice_number": "7", "total_amount": 500.0,
        "currency": "USD", "confidence_score": 0.9}
STRICT = Thresholds(
    runs_per_case=3, field_accuracy_min=0.90, grader_agreement_min=0.85,
    max_errored_cases=0, ci_slice_cases=("inv_gate",), ci_runs_per_case=3,
)


def _model(output: dict[str, Any]) -> FunctionModel:
    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    return FunctionModel(respond)


async def _result_file(output: dict[str, Any], tmp_path: Path) -> Path:
    runs = await run_repeated(_model(output), [CASE], [], runs=3)
    return write_results(runs, "openai/gpt-oss-20b", tmp_path)


def test_committed_thresholds_are_the_preregistered_values() -> None:
    t = load_thresholds()
    assert (t.runs_per_case, t.field_accuracy_min, t.grader_agreement_min) == (
        3, 0.90, 0.85,
    )
    assert t.max_errored_cases == 0
    golden_ids = {c["case_id"] for f in ("invoices.json", "contracts.json")
                  for c in load_golden(f)}
    assert len(t.ci_slice_cases) == 12
    assert set(t.ci_slice_cases) <= golden_ids


def test_repeat_summary_reports_mean_min_max_per_field() -> None:
    runs = [
        {"passed_fields": p, "total_fields": 10,
         "field_results": {"vendor_name": {"passed": p, "total": 10}}}
        for p in (10, 8, 9)
    ]
    summary = repeat_summary(runs)
    assert summary["field_accuracy"] == pytest.approx(
        {"mean": 0.9, "min": 0.8, "max": 1.0}
    )
    assert summary["per_field"]["vendor_name"]["min"] == pytest.approx(0.8)


async def test_run_repeated_extracts_each_case_once_per_run() -> None:
    runs = await run_repeated(_model(GOOD), [CASE], [], runs=3)
    assert len(runs) == 3
    assert all(r.total_cases == 1 for r in runs)


def test_select_cases_refuses_an_unknown_case_id() -> None:
    with pytest.raises(ValueError, match="inv_missing"):
        select_cases([CASE], ["inv_gate", "inv_missing"])


async def test_gate_passes_a_good_run(tmp_path: Path) -> None:
    result = json.loads((await _result_file(GOOD, tmp_path)).read_text())
    assert evaluate_gate(result, STRICT) == []


async def test_gate_fails_when_one_field_breaks(tmp_path: Path) -> None:
    broken = {**GOOD, "vendor_name": "Refund Services Ltd"}
    path = await _result_file(broken, tmp_path)

    failures = evaluate_gate(json.loads(path.read_text()), STRICT)

    assert any("field accuracy" in f for f in failures)
    assert any("vendor_name" in f for f in failures)


async def test_gate_cli_exits_nonzero_on_failure(tmp_path: Path) -> None:
    path = await _result_file({**GOOD, "total_amount": 0.0}, tmp_path)
    assert main([str(path)]) == 1


def test_gate_fails_when_a_case_was_not_measured() -> None:
    result = {"field_accuracy": {"mean": 1.0, "min": 1.0, "max": 1.0},
              "per_field": {},
              "errored_cases": [{"run": 1, "case_id": "c", "error": "429"}]}
    failures = evaluate_gate(result, STRICT)
    assert any("errored" in f for f in failures)


def test_cli_runs_the_ci_slice_three_times(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    from backend.tests.evaluation import run_eval

    monkeypatch.setattr(
        run_eval.llm_client, "get_model", lambda model_name: _model(GOOD)
    )

    run_eval.main(["--slice", "ci", "--output-dir", str(tmp_path)])

    [path] = tmp_path.glob("*-ci.json")
    data = json.loads(path.read_text())
    assert data["runs_per_case"] == 3
    slice_ids = set(load_thresholds().ci_slice_cases)
    assert {c["case_id"] for c in data["cases"]} == slice_ids
    assert "Field accuracy mean" in capsys.readouterr().out
