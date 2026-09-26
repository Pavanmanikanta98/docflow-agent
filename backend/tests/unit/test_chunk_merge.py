"""ADR 006 — merge policies are pure functions, and disagreement is flagged.

No Redis, no LLM.
"""

from backend.core.chunk_merge import merge_chunk_results
from backend.plugins.contract import ContractPlugin
from backend.plugins.invoice import InvoicePlugin


def test_first_non_null_keeps_the_earliest_value():
    plugin = InvoicePlugin()
    chunks = [
        {"vendor_name": "Acme Corp", "confidence_score": 0.9},
        {"vendor_name": None, "confidence_score": 0.9},
        {"vendor_name": None, "confidence_score": 0.9},
    ]
    result = merge_chunk_results(plugin, chunks)
    assert result.fields["vendor_name"] == "Acme Corp"
    assert result.provenance["vendor_name"] == 0
    assert "chunk_conflict:vendor_name" not in result.conflict_reasons


def test_last_keeps_the_final_chunks_total():
    plugin = InvoicePlugin()
    chunks = [
        {"total_amount": 100.0},
        {"total_amount": None},
        {"total_amount": 715.0},
    ]
    result = merge_chunk_results(plugin, chunks)
    assert result.fields["total_amount"] == 715.0
    assert result.provenance["total_amount"] == 2


def test_concat_combines_list_fields_in_chunk_order():
    plugin = InvoicePlugin()
    chunks = [
        {"line_items": ["Widget A - 50.00"]},
        {"line_items": ["Widget B - 50.00"]},
        {"line_items": None},
    ]
    result = merge_chunk_results(plugin, chunks)
    assert result.fields["line_items"] == ["Widget A - 50.00", "Widget B - 50.00"]


def test_concat_combines_string_fields_with_a_separator():
    plugin = ContractPlugin()
    chunks = [
        {"termination_clause": "Either party may terminate with 30 days notice."},
        {"termination_clause": None},
        {"termination_clause": "Termination requires written confirmation."},
    ]
    result = merge_chunk_results(plugin, chunks)
    assert "30 days notice" in result.fields["termination_clause"]
    assert "written confirmation" in result.fields["termination_clause"]


def test_conflicting_scalar_values_are_flagged_but_policy_still_wins():
    """Two chunks disagree on a 'last'-policy field: the policy's answer
    (the later chunk) is kept, and the disagreement is still surfaced."""
    plugin = InvoicePlugin()
    chunks = [
        {"total_amount": 100.0},
        {"total_amount": 250.0},
    ]
    result = merge_chunk_results(plugin, chunks)
    assert result.fields["total_amount"] == 250.0
    assert "chunk_conflict:total_amount" in result.conflict_reasons


def test_conflicting_first_non_null_field_is_flagged():
    plugin = InvoicePlugin()
    chunks = [
        {"vendor_name": "Acme Corp"},
        {"vendor_name": "Different Vendor Inc"},
    ]
    result = merge_chunk_results(plugin, chunks)
    assert result.fields["vendor_name"] == "Acme Corp"  # first wins
    assert "chunk_conflict:vendor_name" in result.conflict_reasons


def test_agreeing_values_are_not_flagged_as_conflicts():
    plugin = InvoicePlugin()
    chunks = [
        {"total_amount": 715.0},
        {"total_amount": 715.0},
    ]
    result = merge_chunk_results(plugin, chunks)
    assert result.fields["total_amount"] == 715.0
    assert result.conflict_reasons == []


def test_concat_fields_never_produce_a_conflict_reason():
    """Multiple different line items across chunks are expected, not a conflict."""
    plugin = InvoicePlugin()
    chunks = [
        {"line_items": ["A"]},
        {"line_items": ["B"]},
    ]
    result = merge_chunk_results(plugin, chunks)
    assert result.conflict_reasons == []


def test_field_missing_from_every_chunk_is_null_not_a_conflict():
    plugin = InvoicePlugin()
    chunks = [{"due_date": None}, {"due_date": None}]
    result = merge_chunk_results(plugin, chunks)
    assert result.fields["due_date"] is None
    assert result.conflict_reasons == []


def test_empty_chunk_list_returns_empty_fields():
    plugin = InvoicePlugin()
    result = merge_chunk_results(plugin, [])
    assert result.fields == {}
    assert result.conflict_reasons == []


def test_metadata_keys_are_never_merged_as_fields():
    plugin = InvoicePlugin()
    chunks = [
        {"vendor_name": "Acme", "_field_confidences": {"vendor_name": 0.9}},
    ]
    result = merge_chunk_results(plugin, chunks)
    assert "_field_confidences" not in result.fields
