"""Agent 3: per-field confidence scoring.

Takes raw text + extracted field values from Agent 2.
Independently verifies each field against the source text.
This prevents the LLM from grading its own extraction work.
"""

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from backend.core.config import settings
from backend.core.token_budget import (
    estimate_tokens,
    get_budget_for_model,
    reserve_or_raise,
)

# ---------------------------------------------------------------------------
# Output schema — generic, works for any document type
# ---------------------------------------------------------------------------

class LLMScores(BaseModel):
    """What the LLM is asked for: per-field scores and an overall score.

    Kept separate from ValidatorOutput so the model cannot set the pipeline status
    or invent review reasons — those are decided by code below.
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
        description=(
            "Optional pipeline status override for hard gates (e.g. 'human_review')."
        ),
    )
    review_reasons: list[str] = Field(
        default_factory=list,
        description="Why the document needs a human: e.g. ['math_mismatch'].",
    )


# ---------------------------------------------------------------------------
# Deterministic gate — runs after the LLM, and outranks it
# ---------------------------------------------------------------------------

MATH_TOLERANCE = 0.01


def _as_float(value: Any) -> float | None:
    """Return a float, or None when the value is missing or not numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def check_arithmetic(extracted_fields: dict[str, Any]) -> list[str]:
    """Check subtotal + tax = total.

    The LLM scores its own extraction, so a confident hallucination can still be
    wrong. This check is arithmetic, not opinion.

    Returns:
        ["math_mismatch"] when all three numbers are present and do not add up,
        [] when they add up or when any of them is missing (a missing subtotal is
        a gap in the document, not proof of a wrong total).
    """
    subtotal = _as_float(extracted_fields.get("subtotal"))
    tax = _as_float(extracted_fields.get("tax_amount"))
    total = _as_float(extracted_fields.get("total_amount"))

    if subtotal is None or tax is None or total is None:
        return []
    if abs((subtotal + tax) - total) > MATH_TOLERANCE:
        return ["math_mismatch"]
    return []


# ---------------------------------------------------------------------------
# The agent — system prompt is document-type agnostic
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a document validation specialist. "
    "You receive the raw text of a document AND the extracted field values "
    "from a previous agent. "
    "For each extracted field, score your confidence that the value is CORRECT "
    "by verifying "
    "it directly against the raw text. "
    "\n\n"
    "Scoring guide:\n"
    "  0.90-1.00: Value is clearly and unambiguously present in the raw text.\n"
    "  0.70-0.89: Value is present but could plausibly be misread.\n"
    "  0.50-0.69: Value is inferred or only partially present.\n"
    "  0.00-0.49: Value is missing, guessed, or not verifiable from the text.\n"
    "\n"
    "Rules:\n"
    "  - Score ONLY the fields listed in the extracted values — do not add or "
    "invent fields.\n"
    "  - overall_confidence is a weighted average; weight monetary and identifier "
    "fields more heavily.\n"
    "  - field_scores must contain exactly the same keys as the extracted values dict."
)

# NOTE: No module-level Agent instance here. The agent is built per call so a
# request that carries its own key uses its own model, without leaking that
# model to any other request.


# ---------------------------------------------------------------------------
# Public function — called by pipeline.py
# ---------------------------------------------------------------------------

async def validate_fields(
    raw_text: str,
    extracted_fields: dict[str, Any],
    model: Any,
    redis_client: Any = None,
) -> ValidatorOutput:
    """
    Validate extracted document fields against the raw source text.

    Works for any document type (invoice, contract, etc.) — the LLM scores
    exactly the fields present in `extracted_fields`, nothing more.

    Args:
        raw_text: The raw text extracted from the PDF by Agent 1 (parser).
        extracted_fields: The structured dict returned by Agent 2 (extractor).
        model: pydantic-ai model instance, resolved by the pipeline (server
            key, or a caller-supplied key when that is enabled).
        redis_client: When given, reserves capacity against ADR 006's token
            budget before calling the model and settles it against the real
            usage afterward. `None` (unit tests with TestModel/FunctionModel)
            skips budgeting — there is no real capacity to protect.

    Returns:
        ValidatorOutput with per-field scores dict and overall_confidence.

    Raises:
        backend.core.token_budget.CapacityWaitError: no room in the budget
            right now.
    """
    field_list = "\n".join(f"  - {k}: {v}" for k, v in extracted_fields.items())
    prompt = (
        f"Raw document text:\n{raw_text}\n\n"
        f"Extracted fields to verify:\n{field_list}\n\n"
        "Score the confidence of each extracted value. "
        "field_scores must contain exactly these keys: "
        f"{list(extracted_fields.keys())}."
    )

    model_name = getattr(model, "model_name", str(model))
    reservation = None
    if redis_client is not None:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        estimated = estimate_tokens(messages, settings.llm_max_completion_tokens)
        reservation = reserve_or_raise(redis_client, model_name, estimated)

    agent = Agent(
        model=model,
        output_type=LLMScores,
        system_prompt=_SYSTEM_PROMPT,
    )

    result = await agent.run(
        prompt, model_settings={"max_tokens": settings.llm_max_completion_tokens}
    )
    scores = result.output

    if reservation is not None:
        usage = result.usage
        actual = (usage.input_tokens or 0) + (usage.output_tokens or 0)
        get_budget_for_model(redis_client, model_name).settle(reservation, actual)

    output = ValidatorOutput(
        field_scores=scores.field_scores,
        overall_confidence=scores.overall_confidence,
    )

    # Deterministic gate: arithmetic beats the model's own confidence.
    reasons = check_arithmetic(extracted_fields)
    if reasons:
        output.overall_confidence = 0.0
        output.status = "human_review"
        output.review_reasons = reasons

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
