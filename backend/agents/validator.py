"""Agent 3: per-field confidence scoring.

Takes raw text + extracted field values from Agent 2.
Independently verifies each field against the source text.
This prevents the LLM from grading its own extraction work.
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from backend.core.llm import llm_client


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class ValidatorOutput(BaseModel):
    """Per-field confidence scores for an invoice extraction.
    Each field is a float from 0.0 to 1.0.
    overall_confidence is a weighted average (weight critical fields more).
    """
    vendor_name: float = Field(..., ge=0.0, le=1.0)
    invoice_number: float = Field(..., ge=0.0, le=1.0)
    invoice_date: float = Field(..., ge=0.0, le=1.0)
    due_date: float = Field(..., ge=0.0, le=1.0)
    total_amount: float = Field(..., ge=0.0, le=1.0)
    currency: float = Field(..., ge=0.0, le=1.0)
    overall_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Weighted average of all field confidences. "
            "Weight total_amount and invoice_number more heavily."
        ),
    )


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------

_validator_agent = Agent(
    model=llm_client.get_model(),
    output_type=ValidatorOutput,
    system_prompt=(
        "You are a document validation specialist. "
        "You receive the raw text of an invoice AND the extracted field values from a previous agent. "
        "For each field, score your confidence that the extracted value is CORRECT by verifying "
        "it directly against the raw text. "
        "\n\n"
        "Scoring guide:\n"
        "  0.90-1.00: Value is clearly and unambiguously present in the raw text.\n"
        "  0.70-0.89: Value is present but could plausibly be misread.\n"
        "  0.50-0.69: Value is inferred or only partially present.\n"
        "  0.00-0.49: Value is missing, guessed, or not verifiable from the text.\n"
        "\n"
        "Set needs_review=true if confidence < 0.75.\n"
        "overall_confidence should weight total_amount and invoice_number more heavily."
    ),
)


# ---------------------------------------------------------------------------
# Public function — called by pipeline.py
# ---------------------------------------------------------------------------

async def validate_invoice_fields(raw_text: str, extracted_fields: dict) -> ValidatorOutput:
    """
    Validate extracted invoice fields against the raw source text.

    Args:
        raw_text: The raw text extracted from the PDF by Agent 1.
        extracted_fields: The structured dict returned by Agent 2.

    Returns:
        ValidatorOutput with per-field scores and overall_confidence.
    """
    prompt = (
        f"Raw invoice text:\n{raw_text}\n\n"
        f"Extracted values to verify:\n{extracted_fields}\n\n"
        "Score the confidence of each extracted value based on whether it appears "
        "correctly and unambiguously in the raw text above."
    )
    result = await _validator_agent.run(prompt)
    return result.output
