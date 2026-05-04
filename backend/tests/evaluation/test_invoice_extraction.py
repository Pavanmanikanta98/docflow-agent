"""Evaluation: Invoice extraction accuracy.

HOW THIS WORKS (read this first):
─────────────────────────────────
1. We load 10 gold-standard invoice texts from golden/invoices.json
2. For EACH invoice, we run extract_fields() with the REAL LLM (Groq)
3. We compare each extracted field against the expected value
4. We report per-field and per-case accuracy

WHEN TO RUN:
   pytest backend/tests/evaluation/test_invoice_extraction.py -v -s
   (the -s flag shows the accuracy reports in real-time)

COST: ~10 LLM API calls per run (one per test case).
      DO NOT run this in CI — run on demand only.

WHAT THE OUTPUT LOOKS LIKE:
   ============================================================
   Case: inv_001_standard
     Clean, well-formatted invoice with all fields present
     Accuracy: 86% (6/7)
     ✅ vendor_name: matched (Acme Corp ≈ Acme Corp)
     ✅ invoice_number: exact match (INV-2026-0042)
     ✅ total_amount: 715.0 ≈ 715.0 (within tolerance)
     ❌ due_date: expected 2026-05-15, got May 15, 2026
     ...
"""

import pytest
from pydantic_ai import Agent

from backend.agents.extractor import extract_fields
from backend.plugins.invoice import InvoicePlugin, InvoiceFields
from backend.core.config import settings

from backend.tests.evaluation.conftest import (
    load_golden,
    fuzzy_match,
    date_match,
    exact_match_number,
    null_match,
    list_overlap_score,
    FieldResult,
    CaseResult,
)


# ---------------------------------------------------------------------------
# Load test data + resolve LLM model
# ---------------------------------------------------------------------------

INVOICE_CASES = load_golden("invoices.json")
PLUGIN = InvoicePlugin()


def _get_model():
    """Build the pydantic-ai model from config.

    WHY A FUNCTION?
    The model depends on settings.llm_provider which reads from .env.
    We resolve it at test time, not import time, so tests can override.
    """
    if settings.llm_provider == "groq":
        return f"groq:{settings.llm_model}"
    elif settings.llm_provider == "openai":
        return f"openai:{settings.llm_model}"
    else:
        return f"groq:{settings.llm_model}"


# ---------------------------------------------------------------------------
# Evaluate a single invoice case
# ---------------------------------------------------------------------------

def evaluate_invoice(result: InvoiceFields, expected: dict) -> CaseResult:
    """Compare extracted fields against expected values.

    THIS IS WHERE THE METRICS COME TOGETHER:
    Each field type gets the appropriate metric:
      - Strings (vendor_name, currency)  → fuzzy_match
      - Numbers (total_amount)           → exact_match_number
      - Dates (invoice_date, due_date)   → fuzzy_match (LLMs format dates differently)
      - Lists (line_items)               → list_overlap_score
      - Nullable fields                  → null_match first, then value check
    """
    fields = []

    # --- vendor_name (fuzzy) ---
    passed = fuzzy_match(result.vendor_name, expected.get("vendor_name"))
    fields.append(FieldResult(
        field_name="vendor_name",
        passed=passed,
        actual=result.vendor_name,
        expected=expected.get("vendor_name"),
        detail=f"{'matched' if passed else 'mismatch'} "
               f"({result.vendor_name} vs {expected.get('vendor_name')})",
    ))

    # --- invoice_number (fuzzy — handles # prefixes, dashes) ---
    passed = fuzzy_match(result.invoice_number, expected.get("invoice_number"))
    fields.append(FieldResult(
        field_name="invoice_number",
        passed=passed,
        actual=result.invoice_number,
        expected=expected.get("invoice_number"),
        detail=f"{'matched' if passed else 'mismatch'} "
               f"({result.invoice_number} vs {expected.get('invoice_number')})",
    ))

    # --- invoice_date (date-aware — "2026-04-15" vs "April 15, 2026") ---
    passed = date_match(result.invoice_date, expected.get("invoice_date"))
    fields.append(FieldResult(
        field_name="invoice_date",
        passed=passed,
        actual=result.invoice_date,
        expected=expected.get("invoice_date"),
        detail=f"{'matched' if passed else 'mismatch'} "
               f"({result.invoice_date} vs {expected.get('invoice_date')})",
    ))

    # --- due_date (null-aware + fuzzy) ---
    exp_due = expected.get("due_date")
    if not null_match(result.due_date, exp_due):
        # One is null, other isn't — that's a fail
        passed = False
        detail = f"null mismatch (got {result.due_date}, expected {exp_due})"
    elif result.due_date is None and exp_due is None:
        passed = True
        detail = "both null ✓"
    else:
        passed = date_match(result.due_date, exp_due)
        detail = f"{'matched' if passed else 'mismatch'} ({result.due_date} vs {exp_due})"
    fields.append(FieldResult(
        field_name="due_date", passed=passed,
        actual=result.due_date, expected=exp_due, detail=detail,
    ))

    # --- total_amount (numeric with tolerance) ---
    passed = exact_match_number(result.total_amount, expected.get("total_amount"))
    fields.append(FieldResult(
        field_name="total_amount",
        passed=passed,
        actual=result.total_amount,
        expected=expected.get("total_amount"),
        detail=f"{'matched' if passed else 'mismatch'} "
               f"({result.total_amount} vs {expected.get('total_amount')})",
    ))

    # --- currency (fuzzy — "USD" vs "usd") ---
    exp_curr = expected.get("currency")
    if not null_match(result.currency, exp_curr):
        passed = False
        detail = f"null mismatch (got {result.currency}, expected {exp_curr})"
    elif result.currency is None and exp_curr is None:
        passed = True
        detail = "both null ✓"
    else:
        passed = fuzzy_match(result.currency, exp_curr)
        detail = f"{'matched' if passed else 'mismatch'} ({result.currency} vs {exp_curr})"
    fields.append(FieldResult(
        field_name="currency", passed=passed,
        actual=result.currency, expected=exp_curr, detail=detail,
    ))

    # --- line_items (list overlap) ---
    exp_items = expected.get("line_items")
    if not null_match(result.line_items, exp_items):
        score = 0.0
        detail = f"null mismatch (got {'list' if result.line_items else 'null'}, expected {'list' if exp_items else 'null'})"
    elif result.line_items is None and exp_items is None:
        score = 1.0
        detail = "both null ✓"
    else:
        score = list_overlap_score(result.line_items, exp_items)
        detail = f"overlap {score:.0%} ({len(result.line_items or [])} extracted, {len(exp_items or [])} expected)"
    # We consider >=50% overlap a pass for line items (they're noisy)
    passed = score >= 0.5
    fields.append(FieldResult(
        field_name="line_items", passed=passed,
        actual=result.line_items, expected=exp_items, detail=detail,
    ))

    return CaseResult(case_id="", description="", field_results=fields)


# ---------------------------------------------------------------------------
# Parametrized test — one test per gold-standard case
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    INVOICE_CASES,
    ids=[c["case_id"] for c in INVOICE_CASES],
)
async def test_invoice_extraction(case: dict) -> None:
    """Run extraction on a single gold-standard invoice and assert accuracy.

    HOW PARAMETRIZE WORKS:
    pytest creates ONE test per case in INVOICE_CASES.
    So you'll see 10 individual test results, not one big blob.
    If inv_005 fails but others pass, you know exactly which case broke.
    """
    model = _get_model()

    # Run the REAL extractor with the REAL LLM
    result = await extract_fields(
        raw_text=case["input"],
        plugin=PLUGIN,
        model=model,
    )

    # Evaluate accuracy
    case_result = evaluate_invoice(result, case["expected"])
    case_result.case_id = case["case_id"]
    case_result.description = case["description"]

    # Print the report (visible with pytest -s)
    print(case_result.summary())

    # PASS/FAIL threshold: at least 60% of fields must be correct.
    # WHY 60%? It's a starting baseline. As you improve prompts,
    # raise this to 70%, then 80%. Track the trend, not perfection.
    assert case_result.accuracy >= 0.6, (
        f"Case {case['case_id']} accuracy too low: "
        f"{case_result.accuracy:.0%} ({case_result.passed_count}/{case_result.total_count})\n"
        f"{case_result.summary()}"
    )
