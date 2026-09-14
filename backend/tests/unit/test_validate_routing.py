"""V1-4: routing after validation — the gate wins, low confidence is explained."""

import pytest

from backend.agents.validator import ValidatorOutput
from backend.core import pipeline
from backend.core.config import settings


def _state() -> pipeline.DocFlowState:
    return {
        "document_id": 1,
        "tenant_id": "t",
        "document_type": "invoice",
        "mime_type": "application/pdf",
        "file_bytes": b"x",
        "raw_text": "INVOICE",
        "extraction_results": {"total_amount": 715.0},
        "confidence_score": None,
        "field_confidences": None,
        "review_reasons": None,
        "human_review_required": None,
        "status": "processing",
        "error": None,
    }


async def _run_validate(
    monkeypatch: pytest.MonkeyPatch, output: ValidatorOutput
) -> pipeline.DocFlowState:
    async def fake_validate(**kwargs: object) -> ValidatorOutput:
        return output

    monkeypatch.setattr(pipeline, "validate_fields", fake_validate)
    monkeypatch.setattr(pipeline, "_resolve_model", lambda document_id: object())
    return await pipeline.validate_node(_state())


async def test_math_mismatch_routes_to_review_with_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = ValidatorOutput(
        field_scores={"total_amount": 0.99},
        overall_confidence=0.0,
        status="human_review",
        review_reasons=["math_mismatch"],
    )

    state = await _run_validate(monkeypatch, output)

    assert state["review_reasons"] == ["math_mismatch"]
    assert pipeline.route_after_validate(state) == "awaiting_review"


async def test_low_confidence_routes_to_review_and_says_the_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    low = max(0.0, settings.confidence_threshold - 0.1)
    output = ValidatorOutput(field_scores={"total_amount": low}, overall_confidence=low)

    state = await _run_validate(monkeypatch, output)

    assert state["review_reasons"] == [f"low_confidence:{low:.2f}"]
    assert pipeline.route_after_validate(state) == "awaiting_review"


async def test_confident_and_consistent_document_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    high = min(1.0, settings.confidence_threshold + 0.1)
    output = ValidatorOutput(
        field_scores={"total_amount": high}, overall_confidence=high
    )

    state = await _run_validate(monkeypatch, output)

    assert state["review_reasons"] == []
    assert pipeline.route_after_validate(state) == "completed"
