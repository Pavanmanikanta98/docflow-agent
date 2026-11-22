"""Issue #39: the evaluation runner scores what the pytest suite scores,
and a rate limit is never recorded as a wrong answer.

No real LLM calls: FunctionModel stands in for the extractor's model.
"""

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from backend.plugins.invoice import InvoiceFields
from backend.tests.evaluation.run_eval import (
    evaluate_single_case,
    run_evaluation,
    scored_fields,
)

INVOICE_CASE: dict[str, Any] = {
    "case_id": "inv_test_no_subtotal",
    "description": "states only a total",
    "input": "INVOICE 7\nFrom: Acme Corp\nTotal: $500.00 USD",
    "expected": {
        # No subtotal / tax_amount key: the invoice states neither.
        "vendor_name": "Acme Corp",
        "invoice_number": "7",
        "invoice_date": None,
        "due_date": None,
        "total_amount": 500.0,
        "currency": "USD",
        "line_items": None,
    },
}

CORRECT_OUTPUT: dict[str, Any] = {
    "vendor_name": "Acme Corp",
    "invoice_number": "7",
    "total_amount": 500.0,
    "currency": "USD",
    "confidence_score": 0.9,
}


def _model_returning(output: dict[str, Any]) -> FunctionModel:
    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tool_name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name, output)])

    return FunctionModel(respond)


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    return sleeps


def test_every_schema_field_except_confidence_is_scored() -> None:
    expected = set(InvoiceFields.model_fields) - {"confidence_score"}
    assert set(scored_fields("invoice")) == expected


async def test_missing_label_means_null_and_an_invented_subtotal_fails() -> None:
    model = _model_returning({**CORRECT_OUTPUT, "subtotal": 500.0})

    result = await evaluate_single_case(INVOICE_CASE, model, "invoice")

    by_name = {fr.field_name: fr for fr in result.field_results}
    assert by_name["subtotal"].passed is False
    assert by_name["subtotal"].expected is None
    assert by_name["subtotal"].actual == 500.0
    assert by_name["tax_amount"].passed is True  # null and null


async def test_field_results_carry_actual_and_expected_values() -> None:
    result = await evaluate_single_case(
        INVOICE_CASE, _model_returning(CORRECT_OUTPUT), "invoice"
    )

    vendor = next(fr for fr in result.field_results if fr.field_name == "vendor_name")
    assert (vendor.actual, vendor.expected) == ("Acme Corp", "Acme Corp")
    assert result.error is None
    assert result.accuracy == 1.0


async def test_rate_limit_is_retried_not_scored_as_wrong(no_sleep: list[float]) -> None:
    calls = {"n": 0}

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ModelHTTPError(429, "test-model", headers={"retry-after": "3"})
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, CORRECT_OUTPUT)]
        )

    results = await run_evaluation(FunctionModel(respond), [INVOICE_CASE], [])

    assert calls["n"] == 2
    assert no_sleep == [pytest.approx(4.0)]
    assert results.errored_cases == []
    assert results.passed_fields == results.total_fields


async def test_case_that_keeps_failing_is_errored_and_left_out_of_accuracy(
    no_sleep: list[float],
) -> None:
    def broken(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(500, "test-model", body="server error")

    good_case = {**INVOICE_CASE, "case_id": "inv_good"}
    calls = {"n": 0}

    def first_breaks(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            return broken(messages, info)
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, CORRECT_OUTPUT)]
        )

    results = await run_evaluation(
        FunctionModel(first_breaks), [INVOICE_CASE, good_case], []
    )

    assert [e["case_id"] for e in results.errored_cases] == ["inv_test_no_subtotal"]
    assert "500" in results.errored_cases[0]["error"]
    scored = len(scored_fields("invoice"))
    assert results.total_fields == scored  # only the good case counts
    assert results.passed_fields == scored
    assert results.total_cases == 1
