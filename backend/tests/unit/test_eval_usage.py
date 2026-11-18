"""Issue #40: every eval run records per-case latency, tokens and cost, and
the configuration that produced it. No real LLM calls."""

from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from backend.plugins.invoice import InvoicePlugin
from backend.tests.evaluation.conftest import CaseResult
from backend.tests.evaluation.run_config import build_run_config, prompt_sha256
from backend.tests.evaluation.run_eval import evaluate_single_case
from backend.tests.evaluation.run_stats import percentile, usage_summary

CASE: dict[str, Any] = {
    "case_id": "inv_usage",
    "description": "",
    "input": "INVOICE 9\nFrom: Acme Corp\nTotal: $10.00",
    "expected": {"vendor_name": "Acme Corp", "total_amount": 10.0},
}


def _model() -> FunctionModel:
    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output = {"vendor_name": "Acme Corp", "total_amount": 10.0,
                  "confidence_score": 0.9}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    return FunctionModel(respond)


async def test_case_records_latency_and_token_usage() -> None:
    result = await evaluate_single_case(CASE, _model(), "invoice")

    assert result.latency_ms is not None and result.latency_ms >= 0
    assert result.input_tokens and result.input_tokens > 0
    assert result.output_tokens and result.output_tokens > 0


def test_percentile_interpolates_between_ranks() -> None:
    values = [100.0, 200.0, 300.0, 400.0]
    assert percentile(values, 50) == pytest.approx(250.0)
    assert percentile(values, 95) == pytest.approx(385.0)
    assert percentile([42.0], 95) == 42.0


def test_percentile_of_nothing_is_none() -> None:
    assert percentile([], 50) is None


def _case(latency: float, tokens_in: int, tokens_out: int) -> CaseResult:
    return CaseResult(
        case_id="c", description="", latency_ms=latency,
        input_tokens=tokens_in, output_tokens=tokens_out,
    )


def test_usage_summary_prices_tokens_from_the_pricing_table() -> None:
    cases = [_case(1000, 1_000_000, 0), _case(3000, 0, 1_000_000)]

    summary = usage_summary(cases, "openai/gpt-oss-20b")

    assert summary["n"] == 2
    assert summary["latency_ms"]["p50"] == pytest.approx(2000.0)
    assert summary["tokens_per_document"]["input_mean"] == pytest.approx(500_000)
    # 1M input at $0.075 + 1M output at $0.30, over two documents
    assert summary["cost_usd"]["per_document_mean"] == pytest.approx(0.1875)
    assert summary["cost_usd"]["per_1000_documents"] == pytest.approx(187.5)
    assert summary["cost_usd"]["pricing_checked"] == "2026-09-24"


def test_usage_summary_says_unpriced_instead_of_guessing() -> None:
    summary = usage_summary([_case(10, 5, 5)], "some/unpriced-model")
    assert summary["cost_usd"] == "not measured: no price for some/unpriced-model"


def test_prompt_hash_changes_when_the_prompt_changes() -> None:
    class EditedPrompt(InvoicePlugin):
        @property
        def system_prompt(self) -> str:
            return super().system_prompt + " Never copy the total into subtotal."

    assert prompt_sha256(InvoicePlugin()) != prompt_sha256(EditedPrompt())
    assert prompt_sha256(InvoicePlugin()) == prompt_sha256(InvoicePlugin())


def test_run_config_names_everything_needed_to_reproduce_the_run() -> None:
    config = build_run_config("openai/gpt-oss-20b")

    assert config["model_id"] == "openai/gpt-oss-20b"
    assert set(config["prompt_sha256"]) == {"invoice", "contract"}
    assert "temperature" in config  # None = provider default, stated explicitly
    assert config["max_tokens"] > 0
    assert config["pydantic_ai_version"]
    assert set(config["golden_sha256"]) == {"invoices.json", "contracts.json"}
    assert "git_commit" in config


async def test_result_file_carries_run_config_usage_and_per_case_tokens(
    tmp_path: Any,
) -> None:
    import json

    from backend.tests.evaluation.run_eval import run_evaluation, write_results

    results = await run_evaluation(_model(), [CASE], [])
    path = write_results([results], "openai/gpt-oss-20b", tmp_path)
    data = json.loads(path.read_text())

    assert data["run_config"]["model_id"] == "openai/gpt-oss-20b"
    assert data["usage"]["n"] == 1
    assert data["cases"][0]["input_tokens"] > 0
    assert data["cases"][0]["latency_ms"] is not None
