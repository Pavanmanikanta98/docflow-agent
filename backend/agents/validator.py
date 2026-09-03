"""Agent 3: per-field confidence scoring.

Takes raw text + extracted field values from Agent 2.
Independently verifies each field against the source text.
This prevents the LLM from grading its own extraction work.
"""

from typing import Any
from pydantic import BaseModel, Field
from pydantic_ai import Agent


# ---------------------------------------------------------------------------
# Output schema — generic, works for any document type
# ---------------------------------------------------------------------------

class ValidatorOutput(BaseModel):
    """
    Per-field confidence scores produced by the validator.

    field_scores: maps each extracted field name to a confidence float [0.0, 1.0].
    overall_confidence: weighted average across all scored fields.
    status: Optional override status for hard gates.
    """
    field_scores: dict[str, float] = Field(
        ...,
        description=(
            "Map of field_name -> confidence score [0.0, 1.0]. "
            "Include exactly the fields present in the extracted values — no extras."
        ),
    )
    overall_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Weighted average of all field confidences. "
            "Weight monetary and identifier fields more heavily."
        ),
    )
    status: str | None = Field(
        None,
        description="Optional pipeline status override for hard gates (e.g. 'human_review').",
    )


# ---------------------------------------------------------------------------
# The agent — system prompt is document-type agnostic
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a document validation specialist. "
    "You receive the raw text of a document AND the extracted field values from a previous agent. "
    "For each extracted field, score your confidence that the value is CORRECT by verifying "
    "it directly against the raw text. "
    "\n\n"
    "Scoring guide:\n"
    "  0.90-1.00: Value is clearly and unambiguously present in the raw text.\n"
    "  0.70-0.89: Value is present but could plausibly be misread.\n"
    "  0.50-0.69: Value is inferred or only partially present.\n"
    "  0.00-0.49: Value is missing, guessed, or not verifiable from the text.\n"
    "\n"
    "Rules:\n"
    "  - Score ONLY the fields listed in the extracted values — do not add or invent fields.\n"
    "  - overall_confidence is a weighted average; weight monetary and identifier fields more heavily.\n"
    "  - field_scores must contain exactly the same keys as the extracted values dict."
)

# NOTE: No module-level Agent instance here. The agent is created per-call
# to support per-tenant BYOK keys (each tenant may use a different model).


# ---------------------------------------------------------------------------
# Public function — called by pipeline.py
# ---------------------------------------------------------------------------

async def validate_fields(
    raw_text: str,
    extracted_fields: dict[str, Any],
    model: Any,
) -> ValidatorOutput:
    """
    Validate extracted document fields against the raw source text.

    Works for any document type (invoice, contract, etc.) — the LLM scores
    exactly the fields present in `extracted_fields`, nothing more.

    Args:
        raw_text: The raw text extracted from the PDF by Agent 1 (parser).
        extracted_fields: The structured dict returned by Agent 2 (extractor).
        model: pydantic-ai model instance (resolved by pipeline — tenant BYOK or fallback).

    Returns:
        ValidatorOutput with per-field scores dict and overall_confidence.
    """
    agent = Agent(
        model=model,
        output_type=ValidatorOutput,
        system_prompt=_SYSTEM_PROMPT,
    )

    field_list = "\n".join(f"  - {k}: {v}" for k, v in extracted_fields.items())
    prompt = (
        f"Raw document text:\n{raw_text}\n\n"
        f"Extracted fields to verify:\n{field_list}\n\n"
        "Score the confidence of each extracted value. "
        "field_scores must contain exactly these keys: "
        f"{list(extracted_fields.keys())}."
    )
    result = await agent.run(prompt)
    output = result.output

    # Hard Gate Validation
    try:
        line_items = extracted_fields.get("line_items")
        total_amount = extracted_fields.get("total_amount")
        tax_amount = extracted_fields.get("tax_amount", 0.0)

        if isinstance(line_items, list) and total_amount is not None:
            sum_lines = 0.0
            for item in line_items:
                if isinstance(item, dict):
                    amt = item.get("amount")
                    if amt is not None:
                        sum_lines += float(amt)

            tax = float(tax_amount) if tax_amount is not None else 0.0
            tot = float(total_amount)

            if abs((sum_lines + tax) - tot) > 0.01:
                output.overall_confidence = 0.0
                output.status = "human_review"
    except (ValueError, TypeError):
        pass

    return output


# ---------------------------------------------------------------------------
# Backward-compat alias — pipeline.py currently calls validate_invoice_fields
# ---------------------------------------------------------------------------

async def validate_invoice_fields(
    raw_text: str,
    extracted_fields: dict[str, Any],
    model: Any,
) -> ValidatorOutput:
    """Deprecated alias — use validate_fields() instead."""
    return await validate_fields(raw_text, extracted_fields, model=model)
