"""Test 2: Extractor returns a valid plugin schema using pydantic-ai TestModel.

No real LLM calls — TestModel generates deterministic dummy output that
satisfies the plugin's extraction_schema."""

import pytest
from pydantic_ai.models.test import TestModel

from backend.agents.extractor import extract_fields
from backend.plugins.invoice import InvoicePlugin, InvoiceFields
from backend.plugins.contract import ContractPlugin


SAMPLE_INVOICE_TEXT = """
INVOICE #INV-2026-0042
Date: 2026-04-15
Due: 2026-05-15

From: Acme Corp
To: Widget Inc.

Items:
- Widget A  x10  $50.00
- Widget B  x5   $30.00

Subtotal: $650.00
Tax (10%): $65.00
Total: $715.00
Currency: USD
"""

SAMPLE_CONTRACT_TEXT = """
SERVICE AGREEMENT

Parties: Acme Corp ("Provider") and Widget Inc. ("Client")
Effective Date: 2026-01-01
Termination Date: 2026-12-31

This agreement governs the provision of consulting services.
Total contract value: $120,000 USD, payable monthly.

Governing Law: State of Delaware
"""


@pytest.mark.asyncio
async def test_extractor_returns_valid_invoice_schema() -> None:
    """extract_fields should return a valid InvoiceFields instance
    when given the invoice plugin and TestModel."""

    plugin = InvoicePlugin()
    model = TestModel()

    result = await extract_fields(
        raw_text=SAMPLE_INVOICE_TEXT,
        plugin=plugin,
        model=model,
    )

    # Result must be an instance of the plugin's extraction schema
    assert isinstance(result, InvoiceFields), (
        f"Expected InvoiceFields, got {type(result).__name__}"
    )

    # confidence_score is always required and must be 0.0–1.0
    assert 0.0 <= result.confidence_score <= 1.0


@pytest.mark.asyncio
async def test_extractor_returns_valid_contract_schema() -> None:
    """Same check but with the contract plugin — proves the extractor
    is truly plugin-agnostic."""

    plugin = ContractPlugin()
    model = TestModel()

    result = await extract_fields(
        raw_text=SAMPLE_CONTRACT_TEXT,
        plugin=plugin,
        model=model,
    )

    schema_cls = plugin.extraction_schema
    assert isinstance(result, schema_cls), (
        f"Expected {schema_cls.__name__}, got {type(result).__name__}"
    )


@pytest.mark.asyncio
async def test_extractor_with_empty_text() -> None:
    """Extractor should still return a valid schema even if the raw text
    is empty — fields will be null but the shape is correct."""

    plugin = InvoicePlugin()
    model = TestModel()

    result = await extract_fields(
        raw_text="",
        plugin=plugin,
        model=model,
    )

    assert isinstance(result, InvoiceFields)
