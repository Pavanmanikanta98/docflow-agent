"""Issue #44: the top extraction error is an invented subtotal. On invoices
that print only a total, the model copied the total into `subtotal` (7 of 21
wrong fields across the 18 Sep runs). The fix is in the invoice plugin: the
model is told, in the system prompt and in the field it fills, to leave
subtotal and tax null unless the document prints them.

These tests capture exactly what the model receives, via FunctionModel."""

from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from backend.agents.extractor import extract_fields
from backend.plugins.invoice import InvoicePlugin

TOTAL_ONLY_INVOICE = "INVOICE 12\nFrom: Maria Chen\nAmount due: $1,500.00"


async def _what_the_model_sees() -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["system"] = " ".join(
            part.content
            for msg in messages if isinstance(msg, ModelRequest)
            for part in msg.parts if isinstance(part, SystemPromptPart)
        )
        seen["schema"] = info.output_tools[0].parameters_json_schema["properties"]
        output = {"total_amount": 1500.0, "confidence_score": 0.8}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    await extract_fields(TOTAL_ONLY_INVOICE, InvoicePlugin(), FunctionModel(respond))
    return seen


async def test_system_prompt_forbids_copying_or_computing_numbers() -> None:
    system = (await _what_the_model_sees())["system"].lower()
    assert "never copy the total into subtotal" in system
    assert "never compute" in system


async def test_subtotal_and_tax_fields_say_null_unless_printed() -> None:
    schema = (await _what_the_model_sees())["schema"]
    for field in ("subtotal", "tax_amount"):
        description = schema[field]["description"].lower()
        assert "printed" in description
        assert "otherwise null" in description
