"""ADR 006 — Groq Batch API: build, upload, submit, poll, then feed the
results through the same validate/route path the real-time worker uses.

NEEDS THE PAID GROQ DEVELOPER TIER. This project runs on the free tier
only (this session's hard rule), so this script is built and unit-tested
against a mocked `groq.Groq` client (see
backend/tests/unit/test_bulk_submit.py) but never run against the real
Batch API. README says so plainly.

JSONL limits and the completion window are Groq's documented Batch API
limits (OpenAI-compatible): at most 50,000 lines / 200MB per file, and a
completion window between 24h and 7d.

Usage (needs a Developer-tier GROQ_API_KEY — not runnable on the free tier):
    uv run python scripts/bulk_submit.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.core.config import settings
from backend.core.pipeline import resolve_validation_outcome
from backend.plugins.base import DocumentPlugin

MAX_BATCH_LINES = 50_000
MAX_BATCH_BYTES = 200 * 1024 * 1024
DEFAULT_COMPLETION_WINDOW = "24h"
BATCH_TERMINAL_STATUSES = frozenset({"completed", "failed", "expired", "cancelled"})


def build_batch_request(
    custom_id: str,
    plugin: DocumentPlugin,
    raw_text: str,
    model: str,
    max_completion_tokens: int,
) -> dict:
    """One JSONL line: an extraction request for one document.

    `custom_id` is how a result is matched back to its document once the
    batch completes — callers should use something like
    f"doc-{document_id}-extract".
    """
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "max_completion_tokens": max_completion_tokens,
            "messages": [
                {"role": "system", "content": plugin.system_prompt},
                {"role": "user", "content": raw_text},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction",
                    "schema": plugin.extraction_schema.model_json_schema(),
                },
            },
        },
    }


def write_batch_jsonl(requests: list[dict], path: Path) -> None:
    """Write the batch requests as JSONL, enforcing Groq's documented limits
    before ever uploading anything."""
    if len(requests) > MAX_BATCH_LINES:
        raise ValueError(
            f"{len(requests)} requests exceeds the {MAX_BATCH_LINES}-line batch limit"
        )
    with path.open("w") as f:
        for request in requests:
            f.write(json.dumps(request) + "\n")

    size = path.stat().st_size
    if size > MAX_BATCH_BYTES:
        raise ValueError(f"{size} bytes exceeds the {MAX_BATCH_BYTES}-byte batch limit")


def submit_batch(
    client: Any, jsonl_path: Path, completion_window: str = DEFAULT_COMPLETION_WINDOW
) -> str:
    """Upload the JSONL file and create the batch job. Returns the batch id."""
    with jsonl_path.open("rb") as f:
        uploaded = client.files.create(file=f, purpose="batch")
    batch = client.batches.create(
        completion_window=completion_window,
        endpoint="/v1/chat/completions",
        input_file_id=uploaded.id,
    )
    return batch.id


def poll_batch(
    client: Any,
    batch_id: str,
    poll_interval_seconds: float = 30.0,
    timeout_seconds: float = 7 * 24 * 3600,
    sleep_fn=time.sleep,
    now_fn=time.time,
) -> Any:
    """Poll until the batch reaches a terminal state (completed/failed/
    expired/cancelled). `sleep_fn`/`now_fn` are injectable so a test can
    drive this without a real 30-second sleep."""
    deadline = now_fn() + timeout_seconds
    while now_fn() < deadline:
        batch = client.batches.retrieve(batch_id)
        if batch.status in BATCH_TERMINAL_STATUSES:
            return batch
        sleep_fn(poll_interval_seconds)
    raise TimeoutError(f"Batch {batch_id} did not reach a terminal state in time")


def download_batch_results(client: Any, output_file_id: str) -> list[dict]:
    """Download the batch's output file and parse it as JSONL."""
    content = client.files.content(output_file_id)
    text = content.text if hasattr(content, "text") else content.read().decode()
    return [json.loads(line) for line in text.strip().splitlines() if line.strip()]


def parse_extraction_from_batch_result(result: dict, plugin: DocumentPlugin):
    """Pull the plugin's schema instance out of one batch result line,
    whichever structured-output form the response used."""
    message = result["response"]["body"]["choices"][0]["message"]
    content = message.get("content")
    if content is None and message.get("tool_calls"):
        content = message["tool_calls"][0]["function"]["arguments"]
    return plugin.extraction_schema.model_validate(json.loads(content))


async def process_batch_results_through_validate_path(
    results: list[dict],
    plugin: DocumentPlugin,
    raw_texts_by_custom_id: dict[str, str],
    model: Any,
    redis_client: Any = None,
) -> dict[str, dict]:
    """The 'feed the results through the same validate/route path' step.

    Reuses backend.agents.validator.validate_fields and
    backend.core.pipeline.resolve_validation_outcome exactly as the
    real-time worker does — a batch-sourced extraction is validated and
    routed by identical rules to a live one, just fed from a downloaded
    result instead of an immediate call.
    """
    from backend.agents.validator import validate_fields

    outcomes: dict[str, dict] = {}
    for result in results:
        custom_id = result["custom_id"]
        fields = parse_extraction_from_batch_result(result, plugin)
        extracted = fields.model_dump(exclude={"confidence_score"})
        raw_text = raw_texts_by_custom_id[custom_id]

        validation = await validate_fields(
            raw_text=raw_text,
            extracted_fields=extracted,
            model=model,
            redis_client=redis_client,
        )
        status, reasons = resolve_validation_outcome(
            validation, settings.confidence_threshold
        )
        outcomes[custom_id] = {
            "status": status,
            "review_reasons": reasons,
            "extraction_results": extracted,
            "confidence_score": validation.overall_confidence,
        }
    return outcomes


def main() -> None:
    raise SystemExit(
        "scripts/bulk_submit.py needs the paid Groq Developer tier for the "
        "Batch API. It is built and unit-tested "
        "(backend/tests/unit/test_bulk_submit.py) but this project runs on "
        "the free tier only, so it has never been run against the real "
        "Batch API — see README's Rate limits and cost section."
    )


if __name__ == "__main__":
    main()
