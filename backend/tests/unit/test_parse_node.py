"""parse_node: failure states for unreadable or unsupported uploads (no LLM, no OCR)."""

import pytest

from backend.core import pipeline


def _state(mime_type: str) -> pipeline.DocFlowState:
    return {
        "document_id": 1,
        "tenant_id": "t",
        "document_type": "invoice",
        "mime_type": mime_type,
        "file_bytes": b"bytes",
        "raw_text": "",
        "extraction_results": None,
        "confidence_score": None,
        "field_confidences": None,
        "human_review_required": None,
        "status": "processing",
        "error": None,
    }


async def test_parse_node_passes_mime_type_and_keeps_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        pipeline, "extract_text", lambda b, mime: seen.append(mime) or "INVOICE 1"
    )

    result = await pipeline.parse_node(_state("image/png"))

    assert seen == ["image/png"]
    assert result["raw_text"] == "INVOICE 1"
    assert result["status"] == "processing"


async def test_parse_node_fails_when_no_text_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline, "extract_text", lambda b, mime: "   ")

    result = await pipeline.parse_node(_state("application/pdf"))

    assert result["status"] == "failed"
    assert "No text could be extracted" in result["error"]


async def test_parse_node_fails_on_unsupported_type() -> None:
    result = await pipeline.parse_node(_state("text/plain"))

    assert result["status"] == "failed"
    assert "Unsupported MIME type" in result["error"]
