"""ADR 006 — chunk splitting respects page boundaries and the token budget.

Pure functions, no Redis, no LLM.
"""

from backend.core.chunking import should_chunk, split_pages_into_chunks
from backend.core.token_budget import estimate_tokens


def test_should_chunk_below_threshold_is_false():
    assert should_chunk(estimated_tokens=100, tpm=8000, max_request_share=0.5) is False


def test_should_chunk_above_threshold_is_true():
    assert should_chunk(estimated_tokens=4001, tpm=8000, max_request_share=0.5) is True


def test_should_chunk_at_exact_threshold_is_false():
    # Strictly greater-than: exactly the share fits in one request.
    assert should_chunk(estimated_tokens=4000, tpm=8000, max_request_share=0.5) is False


def test_split_returns_one_chunk_when_everything_fits():
    pages = ["short page one", "short page two", "short page three"]
    chunks = split_pages_into_chunks(
        pages, system_prompt="extract", max_completion_tokens=100, budget_tokens=5000
    )
    assert chunks == [pages]


def test_split_never_puts_part_of_a_page_in_two_chunks():
    """Every original page string appears whole, in exactly one chunk."""
    pages = [f"page {i} " + ("word " * 200) for i in range(10)]
    chunks = split_pages_into_chunks(
        pages, system_prompt="extract", max_completion_tokens=100, budget_tokens=600
    )
    flattened = [page for chunk in chunks for page in chunk]
    assert flattened == pages  # same pages, same order, none split or dropped


def test_split_respects_the_budget():
    """No chunk's own estimated size (system prompt + pages + completion)
    exceeds the budget, except a single page that alone cannot fit."""
    pages = [f"page {i} " + ("word " * 150) for i in range(8)]
    system_prompt = "You are a document extraction specialist."
    max_completion_tokens = 300
    budget_tokens = 500

    chunks = split_pages_into_chunks(
        pages, system_prompt, max_completion_tokens, budget_tokens
    )

    overhead = estimate_tokens(
        [{"role": "system", "content": system_prompt}], max_completion_tokens
    )
    for chunk in chunks:
        chunk_tokens = overhead + sum(
            estimate_tokens([{"role": "user", "content": page}], 0) for page in chunk
        )
        single_page_alone = len(chunk) == 1
        if not single_page_alone:
            assert chunk_tokens <= budget_tokens


def test_split_gives_an_oversized_lone_page_its_own_chunk():
    """A page whose own text already exceeds the budget still gets a chunk —
    never dropped, never merged with a neighbour that would make it worse."""
    huge_page = "word " * 5000
    pages = ["short intro", huge_page, "short outro"]
    chunks = split_pages_into_chunks(
        pages, system_prompt="extract", max_completion_tokens=100, budget_tokens=500
    )
    assert huge_page in [page for chunk in chunks for page in chunk]
    # The huge page must not be bundled with another page — it alone already
    # exceeds the budget, so any chunk containing it has exactly one page.
    huge_chunk = next(c for c in chunks if huge_page in c)
    assert huge_chunk == [huge_page]


def test_split_handles_empty_pages_list():
    assert split_pages_into_chunks([], "extract", 100, 5000) == []


def test_split_is_deterministic():
    pages = [f"page {i}" for i in range(20)]
    a = split_pages_into_chunks(pages, "extract", 100, 300)
    b = split_pages_into_chunks(pages, "extract", 100, 300)
    assert a == b
