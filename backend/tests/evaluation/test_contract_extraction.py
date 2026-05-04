"""Evaluation: Contract extraction accuracy.

Same pattern as test_invoice_extraction.py but for contracts.
The key difference: contracts have MORE complex fields:
  - parties (list of 2+ entities)
  - key_obligations (list of free-text items)
  - termination_clause (free-text summary — hardest to evaluate)

We use LOOSER thresholds for free-text fields like termination_clause
because there's no single "correct" summary.
"""

import pytest

from backend.agents.extractor import extract_fields
from backend.plugins.contract import ContractPlugin, ContractFields
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
# Load test data
# ---------------------------------------------------------------------------

CONTRACT_CASES = load_golden("contracts.json")
PLUGIN = ContractPlugin()


def _get_model():
    """Build the pydantic-ai model from config."""
    if settings.llm_provider == "groq":
        return f"groq:{settings.llm_model}"
    elif settings.llm_provider == "openai":
        return f"openai:{settings.llm_model}"
    else:
        return f"groq:{settings.llm_model}"


# ---------------------------------------------------------------------------
# Evaluate a single contract case
# ---------------------------------------------------------------------------

def evaluate_contract(result: ContractFields, expected: dict) -> CaseResult:
    """Compare extracted contract fields against expected values.

    CONTRACT-SPECIFIC NOTES:
    ─────────────────────────
    - parties: We check list overlap (fuzzy match each party name)
    - key_obligations: Fuzzy list overlap (these are long sentences)
    - termination_clause: Very loose fuzzy match (0.4 threshold)
      because this is a free-text summary — many valid phrasings exist
    """
    fields = []

    # --- parties (list of names — fuzzy overlap) ---
    exp_parties = expected.get("parties")
    if not null_match(result.parties, exp_parties):
        score = 0.0
        detail = "null mismatch"
    elif result.parties is None and exp_parties is None:
        score = 1.0
        detail = "both null ✓"
    else:
        score = list_overlap_score(result.parties, exp_parties, threshold=0.7)
        detail = f"overlap {score:.0%} ({result.parties} vs {exp_parties})"
    fields.append(FieldResult(
        field_name="parties", passed=score >= 0.5,
        actual=result.parties, expected=exp_parties, detail=detail,
    ))

    # --- effective_date (date-aware) ---
    passed = date_match(result.effective_date, expected.get("effective_date"))
    fields.append(FieldResult(
        field_name="effective_date", passed=passed,
        actual=result.effective_date, expected=expected.get("effective_date"),
        detail=f"{'matched' if passed else 'mismatch'} ({result.effective_date} vs {expected.get('effective_date')})",
    ))

    # --- expiry_date (null-aware + fuzzy) ---
    exp_expiry = expected.get("expiry_date")
    if not null_match(result.expiry_date, exp_expiry):
        passed = False
        detail = f"null mismatch (got {result.expiry_date}, expected {exp_expiry})"
    elif result.expiry_date is None and exp_expiry is None:
        passed = True
        detail = "both null ✓"
    else:
        passed = date_match(result.expiry_date, exp_expiry)
        detail = f"{'matched' if passed else 'mismatch'} ({result.expiry_date} vs {exp_expiry})"
    fields.append(FieldResult(
        field_name="expiry_date", passed=passed,
        actual=result.expiry_date, expected=exp_expiry, detail=detail,
    ))

    # --- contract_value (numeric with tolerance) ---
    exp_value = expected.get("contract_value")
    if not null_match(result.contract_value, exp_value):
        passed = False
        detail = f"null mismatch (got {result.contract_value}, expected {exp_value})"
    elif result.contract_value is None and exp_value is None:
        passed = True
        detail = "both null ✓"
    else:
        passed = exact_match_number(result.contract_value, exp_value)
        detail = f"{'matched' if passed else 'mismatch'} ({result.contract_value} vs {exp_value})"
    fields.append(FieldResult(
        field_name="contract_value", passed=passed,
        actual=result.contract_value, expected=exp_value, detail=detail,
    ))

    # --- currency (fuzzy) ---
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

    # --- jurisdiction (fuzzy — "State of New York" ≈ "New York") ---
    exp_juris = expected.get("jurisdiction")
    if not null_match(result.jurisdiction, exp_juris):
        passed = False
        detail = f"null mismatch (got {result.jurisdiction}, expected {exp_juris})"
    elif result.jurisdiction is None and exp_juris is None:
        passed = True
        detail = "both null ✓"
    else:
        # Loose threshold — "State of New York" vs "New York, NY" are both valid
        passed = fuzzy_match(result.jurisdiction, exp_juris, threshold=0.5)
        detail = f"{'matched' if passed else 'mismatch'} ({result.jurisdiction} vs {exp_juris})"
    fields.append(FieldResult(
        field_name="jurisdiction", passed=passed,
        actual=result.jurisdiction, expected=exp_juris, detail=detail,
    ))

    # --- key_obligations (list of sentences — fuzzy overlap) ---
    exp_oblig = expected.get("key_obligations")
    if not null_match(result.key_obligations, exp_oblig):
        score = 0.0
        detail = f"null mismatch"
    elif result.key_obligations is None and exp_oblig is None:
        score = 1.0
        detail = "both null ✓"
    else:
        # Loose threshold for sentence matching
        score = list_overlap_score(result.key_obligations, exp_oblig, threshold=0.5)
        detail = f"overlap {score:.0%} ({len(result.key_obligations or [])} extracted, {len(exp_oblig or [])} expected)"
    fields.append(FieldResult(
        field_name="key_obligations", passed=score >= 0.4,
        actual=result.key_obligations, expected=exp_oblig, detail=detail,
    ))

    # --- termination_clause (free-text summary — very loose fuzzy) ---
    exp_term = expected.get("termination_clause")
    if not null_match(result.termination_clause, exp_term):
        passed = False
        detail = f"null mismatch (got {result.termination_clause}, expected {exp_term})"
    elif result.termination_clause is None and exp_term is None:
        passed = True
        detail = "both null ✓"
    else:
        # Very loose threshold — many valid ways to summarize a clause
        passed = fuzzy_match(result.termination_clause, exp_term, threshold=0.3)
        detail = f"{'matched' if passed else 'mismatch'} (similarity check at 0.3 threshold)"
        if not passed:
            detail += f"\n       actual:   {result.termination_clause[:100]}..."
            detail += f"\n       expected: {exp_term[:100]}..."
    fields.append(FieldResult(
        field_name="termination_clause", passed=passed,
        actual=result.termination_clause, expected=exp_term, detail=detail,
    ))

    return CaseResult(case_id="", description="", field_results=fields)


# ---------------------------------------------------------------------------
# Parametrized test — one test per gold-standard case
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    CONTRACT_CASES,
    ids=[c["case_id"] for c in CONTRACT_CASES],
)
async def test_contract_extraction(case: dict) -> None:
    """Run extraction on a single gold-standard contract and assert accuracy.

    CONTRACT TESTS ARE HARDER THAN INVOICES:
    - More fields (8 vs 7)
    - Free-text fields (termination_clause, key_obligations)
    - Variable party counts (2-3 parties)

    So we use a lower pass threshold: 50% instead of 60%.
    """
    model = _get_model()

    result = await extract_fields(
        raw_text=case["input"],
        plugin=PLUGIN,
        model=model,
    )

    case_result = evaluate_contract(result, case["expected"])
    case_result.case_id = case["case_id"]
    case_result.description = case["description"]

    print(case_result.summary())

    # Lower threshold for contracts (more free-text fields)
    assert case_result.accuracy >= 0.5, (
        f"Case {case['case_id']} accuracy too low: "
        f"{case_result.accuracy:.0%} ({case_result.passed_count}/{case_result.total_count})\n"
        f"{case_result.summary()}"
    )
