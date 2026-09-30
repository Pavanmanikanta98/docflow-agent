"""V1-4: the arithmetic gate is deterministic and outranks the model's confidence."""

import pytest
import redis as redis_lib
from pydantic_ai.models.test import TestModel

from backend.agents.validator import ValidatorOutput, check_arithmetic, validate_fields
from backend.plugins.invoice import InvoiceFields


def _redis_available() -> bool:
    try:
        client = redis_lib.from_url(
            "redis://localhost:6379/15", socket_connect_timeout=1
        )
        client.ping()
        return True
    except redis_lib.exceptions.RedisError:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(), reason="Redis is not reachable at redis://localhost:6379/15"
)

# ---------------------------------------------------------------------------
# The pure check
# ---------------------------------------------------------------------------

def test_numbers_that_add_up_pass() -> None:
    fields = {"subtotal": 650.0, "tax_amount": 65.0, "total_amount": 715.0}

    assert check_arithmetic(fields) == []


def test_numbers_that_do_not_add_up_are_flagged() -> None:
    fields = {"subtotal": 650.0, "tax_amount": 65.0, "total_amount": 915.0}

    assert check_arithmetic(fields) == ["math_mismatch"]


def test_rounding_inside_one_cent_is_accepted() -> None:
    fields = {"subtotal": 650.0, "tax_amount": 65.0, "total_amount": 715.005}

    assert check_arithmetic(fields) == []


@pytest.mark.parametrize(
    "fields",
    [
        {"total_amount": 715.0},  # nothing to compare
        {"subtotal": 650.0, "total_amount": 715.0},  # no tax line
        {"subtotal": None, "tax_amount": 65.0, "total_amount": 715.0},
        {"subtotal": "n/a", "tax_amount": 65.0, "total_amount": 715.0},
        {},  # a contract, which has none of these fields
    ],
)
def test_missing_or_unusable_numbers_skip_the_gate(fields: dict) -> None:
    """A missing subtotal is a gap in the document, not proof of a wrong total."""
    assert check_arithmetic(fields) == []


# ---------------------------------------------------------------------------
# The gate applied around the LLM call
# ---------------------------------------------------------------------------

class _FakeRun:
    def __init__(self, output: object) -> None:
        self.output = output


async def _validate_with_scores(
    monkeypatch: pytest.MonkeyPatch, fields: dict, confidence: float
) -> ValidatorOutput:
    from backend.agents import validator

    class _FakeAgent:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def run(self, prompt: str, **kwargs: object) -> _FakeRun:
            return _FakeRun(
                validator.LLMScores(
                    field_scores={k: confidence for k in fields},
                    overall_confidence=confidence,
                )
            )

    monkeypatch.setattr(validator, "Agent", _FakeAgent)
    return await validate_fields(
        raw_text="text", extracted_fields=fields, model=object()
    )


async def test_confident_llm_cannot_override_bad_arithmetic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fields = {"subtotal": 650.0, "tax_amount": 65.0, "total_amount": 915.0}

    output = await _validate_with_scores(monkeypatch, fields, confidence=0.99)

    assert output.overall_confidence == 0.0
    assert output.status == "human_review"
    assert output.review_reasons == ["math_mismatch"]


async def test_good_arithmetic_keeps_the_llm_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fields = {"subtotal": 650.0, "tax_amount": 65.0, "total_amount": 715.0}

    output = await _validate_with_scores(monkeypatch, fields, confidence=0.91)

    assert output.overall_confidence == 0.91
    assert output.status is None
    assert output.review_reasons == []


# ---------------------------------------------------------------------------
# The invoice schema carries the numbers the gate needs
# ---------------------------------------------------------------------------

def test_invoice_schema_has_subtotal_and_tax() -> None:
    fields = InvoiceFields(confidence_score=0.5)

    assert fields.subtotal is None
    assert fields.tax_amount is None


# ---------------------------------------------------------------------------
# ADR 006 — capacity reservation/settlement, against real Redis + TestModel
# ---------------------------------------------------------------------------

@requires_redis
@pytest.mark.asyncio
async def test_validate_fields_reserves_and_settles_capacity_against_real_redis() -> (
    None
):
    """With a redis_client, validate_fields must reserve and settle without
    raising — the same `result.usage` property access bug the extractor had
    (caught by scripts/load_test.py) applies here too."""
    client = redis_lib.from_url("redis://localhost:6379/15")
    client.flushdb()

    output = await validate_fields(
        raw_text="INVOICE total 715.00",
        extracted_fields={"total_amount": 715.0},
        model=TestModel(),
        redis_client=client,
    )

    assert isinstance(output, ValidatorOutput)
    keys = client.keys("token_budget:*:tpm:*")
    assert keys, "expected the reservation to have written a tpm window key"
    client.flushdb()
