"""Stage 1: extract raw text from an uploaded document.

PDFs use a 3-tier fallback:
  1. PyMuPDF  — fast, handles digital PDFs
  2. pdfplumber — catches edge cases PyMuPDF misses
  3. Tesseract OCR — handles scanned/image-based PDFs

Images (PNG, JPEG) go straight to Tesseract OCR.

Returns the first non-empty result. If everything fails, returns "".
"""

import io

import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image


def _try_pymupdf_pages(file_bytes: bytes) -> list[str]:
    """Tier 1, page-preserving: one entry per page (blank pages included)."""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        return [page.get_text() for page in doc]


def _try_pymupdf(file_bytes: bytes) -> str:
    """Tier 1: PyMuPDF text extraction — fastest for digital PDFs."""
    return "\n".join(p for p in _try_pymupdf_pages(file_bytes) if p.strip())


def _try_pdfplumber_pages(file_bytes: bytes) -> list[str]:
    """Tier 2, page-preserving: one entry per page (blank pages included)."""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        return [(page.extract_text() or "") for page in pdf.pages]


def _try_pdfplumber(file_bytes: bytes) -> str:
    """Tier 2: pdfplumber — better at table-heavy or complex layouts."""
    return "\n".join(p for p in _try_pdfplumber_pages(file_bytes) if p.strip())


def _try_tesseract_pages(file_bytes: bytes) -> list[str]:
    """Tier 3, page-preserving: one entry per page (blank pages included)."""
    pages = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            # Render the page as an image at 300 DPI for good OCR accuracy
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pages.append(pytesseract.image_to_string(img))
    return pages


def _try_tesseract(file_bytes: bytes) -> str:
    """Tier 3: Tesseract OCR — converts page images to text for scanned PDFs."""
    return "\n".join(p for p in _try_tesseract_pages(file_bytes) if p.strip())


def extract_pages_from_pdf(file_bytes: bytes) -> list[str]:
    """PDF path, page-preserving. Same 3-tier fallback as
    extract_text_from_pdf, but keeps page boundaries — the chunker (ADR 006)
    splits large documents at page boundaries, never mid-page.

    Returns the first tier with any non-blank page, or [] if all fail.
    """
    pages = _try_pymupdf_pages(file_bytes)
    if any(p.strip() for p in pages):
        return pages

    pages = _try_pdfplumber_pages(file_bytes)
    if any(p.strip() for p in pages):
        return pages

    pages = _try_tesseract_pages(file_bytes)
    if any(p.strip() for p in pages):
        return pages

    return []


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    PDF path. Tries 3 extraction methods in order.
    Returns the first non-empty result, or "" if all fail.
    """
    return "\n".join(p for p in extract_pages_from_pdf(file_bytes) if p.strip())


IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg"})
PDF_MIME_TYPE = "application/pdf"


def extract_text_from_image(file_bytes: bytes) -> str:
    """OCR a single PNG/JPEG image with Tesseract."""
    with Image.open(io.BytesIO(file_bytes)) as img:
        return pytesseract.image_to_string(img.convert("RGB"))


def extract_pages(file_bytes: bytes, mime_type: str) -> list[str]:
    """Page-preserving counterpart to extract_text (ADR 006 chunking).

    An image has exactly one "page" — the whole image.

    Raises:
        ValueError: if the MIME type is not a supported document type.
    """
    if mime_type in IMAGE_MIME_TYPES:
        return [extract_text_from_image(file_bytes)]
    if mime_type == PDF_MIME_TYPE:
        return extract_pages_from_pdf(file_bytes)
    raise ValueError(f"Unsupported MIME type for parsing: {mime_type!r}")


def extract_text(file_bytes: bytes, mime_type: str) -> str:
    """Pick the extraction path from the upload's MIME type.

    Raises:
        ValueError: if the MIME type is not a supported document type.
    """
    if mime_type in IMAGE_MIME_TYPES:
        return extract_text_from_image(file_bytes)
    if mime_type == PDF_MIME_TYPE:
        return extract_text_from_pdf(file_bytes)
    raise ValueError(f"Unsupported MIME type for parsing: {mime_type!r}")


if __name__ == "__main__":
    """Standalone test: python -m backend.agents.parser <path_to_pdf>"""
    import sys

    if len(sys.argv) != 2:
        print("Usage: python -m backend.agents.parser <path_to_pdf>")
        sys.exit(1)
    with open(sys.argv[1], "rb") as f:
        raw_bytes = f.read()

    extracted = extract_text_from_pdf(raw_bytes)
    print("--- Extracted Text ---")
    print(extracted[:2000])
    print(f"\n--- TOTAL CHARACTERS EXTRACTED: {len(extracted)} ---")
