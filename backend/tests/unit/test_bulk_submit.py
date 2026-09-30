"""ADR 006 — scripts/bulk_submit.py (Groq Batch API), tested against a
mocked `groq.Groq` client only. The real Batch API needs the paid
Developer tier this project does not have (see the script's own docstring
and README) — nothing here makes a real HTTP call.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic_ai.models.test import TestModel

from backend.plugins.invoice import InvoicePlugin
from scripts.bulk_submit import (
    MAX_BATCH_LINES,
    build_batch_request,
    download_batch_results,
    parse_extraction_from_batch_result,
    poll_batch,
    process_batch_results_through_validate_path,
    submit_batch,
    write_batch_jsonl,
)


def test_build_batch_request_shape():
    plugin = InvoicePlugin()
    request = build_batch_request(
        custom_id="doc-1-extract",
        plugin=plugin,
        raw_text="INVOICE total 715.00",
        model="openai/gpt-oss-20b",
        max_completion_tokens=300,
    )
    assert request["custom_id"] == "doc-1-extract"
    assert request["method"] == "POST"
    assert request["url"] == "/v1/chat/completions"
    assert request["body"]["model"] == "openai/gpt-oss-20b"
    assert request["body"]["max_completion_tokens"] == 300
    assert request["body"]["messages"][0]["role"] == "system"
    assert request["body"]["messages"][1]["content"] == "INVOICE total 715.00"
    schema_name = request["body"]["response_format"]["json_schema"]["name"]
    assert schema_name == "extraction"


def test_write_batch_jsonl_writes_one_line_per_request(tmp_path):
    requests = [{"custom_id": f"doc-{i}"} for i in range(5)]
    path = tmp_path / "batch.jsonl"
    write_batch_jsonl(requests, path)

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 5
    assert json.loads(lines[0])["custom_id"] == "doc-0"


def test_write_batch_jsonl_rejects_too_many_lines(tmp_path):
    requests = [{"custom_id": str(i)} for i in range(MAX_BATCH_LINES + 1)]
    with pytest.raises(ValueError, match="line batch limit"):
        write_batch_jsonl(requests, tmp_path / "batch.jsonl")


def test_write_batch_jsonl_rejects_oversized_file(tmp_path, monkeypatch):
    # Avoid actually writing 200MB: shrink the limit instead of the data.
    monkeypatch.setattr("scripts.bulk_submit.MAX_BATCH_BYTES", 10)
    with pytest.raises(ValueError, match="byte batch limit"):
        write_batch_jsonl([{"custom_id": "doc-1"}], tmp_path / "batch.jsonl")


def test_submit_batch_uploads_then_creates(tmp_path):
    path = tmp_path / "batch.jsonl"
    write_batch_jsonl([{"custom_id": "doc-1"}], path)

    client = MagicMock()
    client.files.create.return_value = SimpleNamespace(id="file-abc")
    client.batches.create.return_value = SimpleNamespace(id="batch-xyz")

    batch_id = submit_batch(client, path)

    assert batch_id == "batch-xyz"
    client.files.create.assert_called_once()
    assert client.files.create.call_args.kwargs["purpose"] == "batch"
    client.batches.create.assert_called_once_with(
        completion_window="24h",
        endpoint="/v1/chat/completions",
        input_file_id="file-abc",
    )


def test_poll_batch_returns_on_terminal_status():
    client = MagicMock()
    client.batches.retrieve.side_effect = [
        SimpleNamespace(status="validating"),
        SimpleNamespace(status="in_progress"),
        SimpleNamespace(status="completed", output_file_id="file-out"),
    ]

    sleeps = []
    result = poll_batch(
        client,
        "batch-xyz",
        poll_interval_seconds=1,
        sleep_fn=sleeps.append,
        now_fn=lambda: 0.0,
    )

    assert result.status == "completed"
    assert sleeps == [1, 1]  # slept between the two non-terminal polls


def test_poll_batch_times_out_without_a_terminal_status():
    client = MagicMock()
    client.batches.retrieve.return_value = SimpleNamespace(status="in_progress")

    fake_time = {"t": 0.0}

    def now_fn():
        return fake_time["t"]

    def sleep_fn(seconds):
        fake_time["t"] += seconds

    with pytest.raises(TimeoutError):
        poll_batch(
            client,
            "batch-xyz",
            poll_interval_seconds=10,
            timeout_seconds=25,
            sleep_fn=sleep_fn,
            now_fn=now_fn,
        )


def test_download_batch_results_parses_jsonl():
    client = MagicMock()
    client.files.content.return_value = SimpleNamespace(
        text='{"custom_id": "doc-1"}\n{"custom_id": "doc-2"}\n'
    )
    results = download_batch_results(client, "file-out")
    assert [r["custom_id"] for r in results] == ["doc-1", "doc-2"]


def test_parse_extraction_from_batch_result_content_form():
    plugin = InvoicePlugin()
    result = {
        "custom_id": "doc-1",
        "response": {
            "body": {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "vendor_name": "Acme",
                                    "confidence_score": 0.9,
                                }
                            )
                        }
                    }
                ]
            }
        },
    }
    fields = parse_extraction_from_batch_result(result, plugin)
    assert fields.vendor_name == "Acme"


def test_parse_extraction_from_batch_result_tool_call_form():
    plugin = InvoicePlugin()
    result = {
        "custom_id": "doc-1",
        "response": {
            "body": {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "function": {
                                        "arguments": json.dumps(
                                            {
                                                "vendor_name": "Acme",
                                                "confidence_score": 0.9,
                                            }
                                        )
                                    }
                                }
                            ],
                        }
                    }
                ]
            }
        },
    }
    fields = parse_extraction_from_batch_result(result, plugin)
    assert fields.vendor_name == "Acme"


async def test_process_batch_results_through_validate_path():
    plugin = InvoicePlugin()
    results = [
        {
            "custom_id": "doc-1",
            "response": {
                "body": {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "total_amount": 715.0,
                                        "confidence_score": 0.9,
                                    }
                                )
                            }
                        }
                    ]
                }
            },
        }
    ]
    outcomes = await process_batch_results_through_validate_path(
        results,
        plugin,
        raw_texts_by_custom_id={"doc-1": "INVOICE total 715.00"},
        model=TestModel(),
    )
    assert "doc-1" in outcomes
    assert outcomes["doc-1"]["status"] in ("completed", "awaiting_review")
    assert outcomes["doc-1"]["extraction_results"]["total_amount"] == 715.0
