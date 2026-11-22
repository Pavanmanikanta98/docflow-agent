"""Issue #65: one malformed model reply must not fail a whole document.

With the real gpt-oss-20b the validate pass once returned a truncated tool
call and the document failed after a single retry. FunctionModel stands in
for the model; no real LLM calls."""

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from backend.agents.extractor import extract_fields
from backend.agents.validator import validate_fields
from backend.plugins.invoice import InvoiceFields, InvoicePlugin

VALID_EXTRACTION = {"vendor_name": "Acme", "total_amount": 5.0, "confidence_score": 0.9}
VALID_SCORES = {"field_scores": {"vendor_name": 0.9}, "overall_confidence": 0.9}
TRUNCATED = '{"field"'  # what the real model sent: cut off mid-object


def _flaky_model(bad_replies: int, good_args: dict) -> tuple[FunctionModel, dict]:
    """Return `bad_replies` malformed tool calls, then a valid one."""
    calls = {"n": 0}

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        args = TRUNCATED if calls["n"] <= bad_replies else good_args
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])

    return FunctionModel(respond), calls


async def test_extractor_survives_two_malformed_replies() -> None:
    model, calls = _flaky_model(2, VALID_EXTRACTION)

    fields = await extract_fields("INVOICE", InvoicePlugin(), model)

    assert isinstance(fields, InvoiceFields)
    assert calls["n"] == 3


async def test_validator_survives_two_malformed_replies() -> None:
    model, calls = _flaky_model(2, VALID_SCORES)

    out = await validate_fields("INVOICE", {"vendor_name": "Acme"}, model)

    assert out.overall_confidence == pytest.approx(0.9)
    assert calls["n"] == 3


async def test_a_model_that_never_recovers_still_fails_clearly() -> None:
    model, calls = _flaky_model(10_000, VALID_SCORES)

    with pytest.raises(UnexpectedModelBehavior):
        await validate_fields("INVOICE", {"vendor_name": "Acme"}, model)

    assert calls["n"] < 10  # bounded: a retry limit, not an endless loop
