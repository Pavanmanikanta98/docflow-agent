"""ADR 006 — pure aggregation of measured token usage for the cost report."""

from backend.core.cost_aggregation import (
    TokenUsageCase,
    aggregate_by_document_type,
    load_cases_from_result,
)


def test_load_cases_from_a_well_formed_results_file():
    data = {
        "cases": [
            {"document_type": "invoice", "input_tokens": 400, "output_tokens": 60},
            {"document_type": "contract", "input_tokens": 900, "output_tokens": 120},
        ]
    }
    cases = load_cases_from_result(data)
    assert cases == [
        TokenUsageCase("invoice", 400, 60),
        TokenUsageCase("contract", 900, 120),
    ]


def test_load_cases_returns_empty_for_a_file_with_no_cases_key():
    """e.g. evals/results/<date>-load-test.json, which measures wait times
    rather than token usage — it must not be misread as cost data."""
    data = {"failures": 0, "pass": True, "small_doc_wait_seconds": {"p50": 70.5}}
    assert load_cases_from_result(data) == []


def test_load_cases_skips_incomplete_entries():
    data = {
        "cases": [
            {"document_type": "invoice", "input_tokens": 400, "output_tokens": 60},
            {"document_type": "invoice", "input_tokens": 400},  # missing output_tokens
            "not even a dict",
        ]
    }
    cases = load_cases_from_result(data)
    assert cases == [TokenUsageCase("invoice", 400, 60)]


def test_aggregate_groups_by_document_type():
    cases = [
        TokenUsageCase("invoice", 400, 60),
        TokenUsageCase("invoice", 600, 100),
        TokenUsageCase("contract", 2000, 300),
    ]
    stats = aggregate_by_document_type(cases)

    assert set(stats.keys()) == {"invoice", "contract"}
    assert stats["invoice"].count == 2
    assert stats["invoice"].median_input == 500
    assert stats["contract"].count == 1


def test_aggregate_of_empty_cases_is_empty():
    assert aggregate_by_document_type([]) == {}


def test_p95_uses_the_highest_value_for_small_samples():
    cases = [TokenUsageCase("invoice", n, n) for n in (100, 200, 300, 400, 500)]
    stats = aggregate_by_document_type(cases)
    assert stats["invoice"].p95_input == 500
