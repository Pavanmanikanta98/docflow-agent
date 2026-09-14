"""Parser: scanned PDFs fall through to OCR; image uploads go straight to OCR.

No LLM calls. Needs the `tesseract` binary; skipped with a reason if it is missing.
"""

import io
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont

from backend.agents import parser
from backend.agents.parser import _try_pymupdf, extract_text_from_pdf

requires_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="tesseract binary not installed (apt-get install tesseract-ocr)",
)


def _image_only_pdf(text: str) -> bytes:
    """Build a one-page PDF that contains only a picture of `text` — no text layer."""
    img = Image.new("RGB", (1200, 300), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=72)
    draw.text((40, 100), text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=150)
    return buf.getvalue()


def test_image_only_pdf_has_no_text_layer() -> None:
    """Guard for the fixture: PyMuPDF finds nothing, so OCR is the only way in."""
    assert _try_pymupdf(_image_only_pdf("INVOICE 4821")).strip() == ""


@requires_tesseract
def test_scanned_pdf_is_read_with_ocr() -> None:
    text = extract_text_from_pdf(_image_only_pdf("INVOICE 4821"))

    assert "INVOICE" in text.upper()
    assert "4821" in text


def _png(text: str) -> bytes:
    img = Image.new("RGB", (1200, 300), "white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 100), text, fill="black", font=ImageFont.load_default(size=72))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _record_paths(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace both extraction paths with stubs that record which one ran."""
    calls: list[str] = []

    def fake_ocr(file_bytes: bytes) -> str:
        calls.append("ocr")
        return "x"

    def fake_pdf(file_bytes: bytes) -> str:
        calls.append("pdf")
        return "x"

    monkeypatch.setattr(parser, "extract_text_from_image", fake_ocr)
    monkeypatch.setattr(parser, "extract_text_from_pdf", fake_pdf)
    return calls


@pytest.mark.parametrize("mime_type", ["image/png", "image/jpeg"])
def test_images_go_to_ocr_not_the_pdf_path(
    monkeypatch: pytest.MonkeyPatch, mime_type: str
) -> None:
    calls = _record_paths(monkeypatch)

    parser.extract_text(b"bytes", mime_type)

    assert calls == ["ocr"]


def test_pdfs_go_to_the_pdf_path(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record_paths(monkeypatch)

    parser.extract_text(b"%PDF-1.4", "application/pdf")

    assert calls == ["pdf"]


def test_unsupported_mime_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported MIME type"):
        parser.extract_text(b"hello", "text/plain")


@requires_tesseract
def test_png_upload_is_read_with_ocr() -> None:
    text = parser.extract_text(_png("INVOICE 4821"), "image/png")

    assert "INVOICE" in text.upper()
    assert "4821" in text
