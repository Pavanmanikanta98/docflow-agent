"""ADR 006 — split an over-budget document into page-respecting chunks.

Pure functions only: no Redis, no LLM calls. `backend.queue.worker` decides
*when* to chunk (using `should_chunk`) and orchestrates the per-chunk ARQ
jobs; this module only decides *how* to split.
"""

from __future__ import annotations

from backend.core.token_budget import estimate_tokens


def should_chunk(estimated_tokens: int, tpm: int, max_request_share: float) -> bool:
    """True when a single request would exceed the configured share of TPM."""
    return estimated_tokens > max_request_share * tpm


def split_pages_into_chunks(
    pages: list[str],
    system_prompt: str,
    max_completion_tokens: int,
    budget_tokens: int,
) -> list[list[str]]:
    """Group whole pages into chunks that each fit under `budget_tokens`.

    Never splits a page — a chunk is always a contiguous run of whole pages,
    so a merge policy can treat "which chunk this came from" as meaningful
    provenance. A single page whose own text already exceeds the budget
    still gets its own (over-budget) chunk: sentence-level splitting is out
    of scope, and sending it alone is strictly better than either dropping
    it or blocking every other chunk on a page that will never fit.

    Args:
        pages: one string per source page, in order (may include blanks).
        system_prompt: charged against every chunk's budget as fixed overhead.
        max_completion_tokens: the reply budget reserved on every call.
        budget_tokens: the token ceiling each chunk's request must fit under.

    Returns:
        A list of chunks, each a list of the original page strings it contains,
        in page order. Never empty unless `pages` is empty.
    """
    if not pages:
        return []

    overhead = estimate_tokens(
        [{"role": "system", "content": system_prompt}], max_completion_tokens
    )
    page_tokens = [
        estimate_tokens([{"role": "user", "content": page}], 0) for page in pages
    ]

    chunks: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0

    for page, tokens in zip(pages, page_tokens):
        projected = overhead + current_tokens + tokens
        if current and projected > budget_tokens:
            chunks.append(current)
            current = []
            current_tokens = 0
        current.append(page)
        current_tokens += tokens

    if current:
        chunks.append(current)

    return chunks
