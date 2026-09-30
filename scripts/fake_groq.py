"""ADR 006 — a local, OpenAI/Groq-compatible server for load-testing the
token budget without spending real free-tier capacity.

Enforces a fixed TPM/RPM ceiling (defaults match the Groq free tier), and
responds the same way the real API does at each edge:
  - under budget: 200, with `x-ratelimit-*` headers showing what's left.
  - over the per-minute ceiling: 429, `retry-after` + `x-ratelimit-*`
    headers, same header names and duration format confirmed live against
    api.groq.com (see backend/core/token_budget.py).
  - a single request whose own estimated size exceeds the WHOLE TPM budget:
    413 "request too large" — no amount of waiting fixes that one, so it is
    a different error class from a 429.

Run it, then point the pipeline at it:
    python scripts/fake_groq.py --port 8899 --tpm 8000 --rpm 30
    GROQ_API_KEY=fake-key GROQ_BASE_URL=http://localhost:8899/openai/v1 \\
        uv run python scripts/load_test.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import tiktoken
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

ENCODING = "o200k_base"


def _minimal_json_instance(schema: dict[str, Any]) -> Any:
    """Build the smallest value satisfying a JSON schema fragment.

    pydantic-ai asks Groq for structured output via tool-calling: it sends
    the extraction schema (InvoiceFields/ContractFields/LLMScores) as a
    tool's `parameters`, and expects `tool_calls[0].function.arguments` back
    as a JSON object matching it. This walks that schema generically —
    required properties only, defaults for everything else — so the same
    fake server works for any of the pipeline's document-type schemas
    without hardcoding field names.
    """
    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            if branch.get("type") != "null":
                return _minimal_json_instance(branch)
        return None

    schema_type = schema.get("type")

    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        return {
            name: _minimal_json_instance(sub)
            for name, sub in properties.items()
            if name in required
        }
    if schema_type == "array":
        return []
    if schema_type == "string":
        enum = schema.get("enum")
        return enum[0] if enum else "x"
    if schema_type in ("number", "integer"):
        value = schema.get("minimum", 0) or 0
        maximum = schema.get("maximum")
        if maximum is not None and value > maximum:
            value = maximum
        return value
    if schema_type == "boolean":
        return False
    return None


@dataclass
class _WindowState:
    minute_bucket: int = -1
    tokens_used: int = 0
    requests_used: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _estimate_request_tokens(body: dict) -> tuple[int, int]:
    """Return (prompt_tokens_estimate, requested_completion_tokens)."""
    enc = tiktoken.get_encoding(ENCODING)
    prompt_tokens = 0
    for message in body.get("messages", []):
        prompt_tokens += 4
        prompt_tokens += len(enc.encode(str(message.get("content", ""))))
    completion_tokens = (
        body.get("max_completion_tokens") or body.get("max_tokens") or 1024
    )
    return prompt_tokens, completion_tokens


def create_app(tpm: int, rpm: int) -> FastAPI:
    app = FastAPI(title="fake-groq")
    state = _WindowState()

    def _current_minute_bucket() -> int:
        return int(time.time() // 60)

    async def _roll_window_if_needed() -> None:
        bucket = _current_minute_bucket()
        if state.minute_bucket != bucket:
            state.minute_bucket = bucket
            state.tokens_used = 0
            state.requests_used = 0

    def _seconds_left_in_window() -> float:
        return (state.minute_bucket + 1) * 60 - time.time()

    def _ratelimit_headers(remaining_tokens: int, remaining_requests: int) -> dict:
        reset_s = max(_seconds_left_in_window(), 0.0)
        return {
            "x-ratelimit-limit-tokens": str(tpm),
            "x-ratelimit-remaining-tokens": str(max(remaining_tokens, 0)),
            "x-ratelimit-reset-tokens": f"{reset_s:.3f}s",
            "x-ratelimit-limit-requests": str(rpm),
            "x-ratelimit-remaining-requests": str(max(remaining_requests, 0)),
            "x-ratelimit-reset-requests": f"{reset_s:.3f}s",
        }

    @app.post("/openai/v1/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        model = body.get("model", "openai/gpt-oss-20b")
        prompt_tokens, requested_completion = _estimate_request_tokens(body)
        estimated_total = prompt_tokens + requested_completion

        if estimated_total > tpm:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "message": (
                            f"Request too large for model `{model}` on tokens "
                            f"per minute (TPM): Limit {tpm}, Requested "
                            f"{estimated_total}."
                        ),
                        "type": "tokens",
                        "code": "request_too_large",
                    }
                },
            )

        async with state.lock:
            await _roll_window_if_needed()

            would_exceed_tokens = state.tokens_used + estimated_total > tpm
            would_exceed_requests = state.requests_used + 1 > rpm

            if would_exceed_tokens or would_exceed_requests:
                retry_after = max(_seconds_left_in_window(), 0.0)
                headers = _ratelimit_headers(
                    tpm - state.tokens_used, rpm - state.requests_used
                )
                headers["retry-after"] = f"{retry_after:.0f}"
                return JSONResponse(
                    status_code=429,
                    headers=headers,
                    content={
                        "error": {
                            "message": "Rate limit reached for this model.",
                            "type": "tokens" if would_exceed_tokens else "requests",
                            "code": "rate_limit_exceeded",
                        }
                    },
                )

            state.tokens_used += estimated_total
            state.requests_used += 1
            headers = _ratelimit_headers(
                tpm - state.tokens_used, rpm - state.requests_used
            )

        completion_tokens = min(requested_completion, 64)
        message: dict[str, Any] = {"role": "assistant", "content": None}
        finish_reason = "stop"

        tools = body.get("tools") or []
        if tools:
            tool = tools[0]["function"]
            arguments = _minimal_json_instance(tool.get("parameters", {}))
            message["tool_calls"] = [
                {
                    "id": f"call_{uuid.uuid4().hex[:12]}",
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "arguments": json.dumps(arguments),
                    },
                }
            ]
            finish_reason = "tool_calls"
        else:
            message["content"] = "ok"

        return JSONResponse(
            status_code=200,
            headers=headers,
            content={
                "id": f"chatcmpl-fake-{uuid.uuid4().hex[:12]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {"index": 0, "message": message, "finish_reason": finish_reason}
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            },
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--tpm", type=int, default=8000)
    parser.add_argument("--rpm", type=int, default=30)
    args = parser.parse_args()

    app = create_app(tpm=args.tpm, rpm=args.rpm)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
