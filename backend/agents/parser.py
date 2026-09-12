"""Stage 1: extract raw text from an uploaded document.

PDFs use a 3-tier fallback:
  1. PyMuPDF  — fast, handles digital PDFs
  2. pdfplumber — catches edge cases PyMuPDF misses
  3. Tesseract OCR — handles scanned/image-based PDFs

Images (PNG, JPEG) go straight to Tesseract OCR.

Returns the first non-empty result. If everything fails, returns "".
"""

import io
import fitz            # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image


def _try_pymupdf(file_bytes: bytes) -> str:
    """Tier 1: PyMuPDF text extraction — fastest for digital PDFs."""
    text_parts = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text = page.get_text()
            if text.strip():
                text_parts.append(text)
    return "\n".join(text_parts)


def _try_pdfplumber(file_bytes: bytes) -> str:
    """Tier 2: pdfplumber — better at table-heavy or complex layouts."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text and text.strip():
                text_parts.append(text)
    return "\n".join(text_parts)


def _try_tesseract(file_bytes: bytes) -> str:
    """Tier 3: Tesseract OCR — converts page images to text for scanned PDFs."""
    text_parts = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            # Render the page as an image at 300 DPI for good OCR accuracy
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img)
            if text.strip():
                text_parts.append(text)
    return "\n".join(text_parts)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    PDF path. Tries 3 extraction methods in order.
    Returns the first non-empty result, or "" if all fail.
    """
    # Tier 1: PyMuPDF (fast, digital PDFs)
    text = _try_pymupdf(file_bytes)
    if text.strip():
        return text

    # Tier 2: pdfplumber (complex layouts)
    text = _try_pdfplumber(file_bytes)
    if text.strip():
        return text

    # Tier 3: Tesseract OCR (scanned/image PDFs)
    text = _try_tesseract(file_bytes)
    if text.strip():
        return text

    # All 3 failed — return empty string, pipeline will mark as failed
    return ""


IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg"})
PDF_MIME_TYPE = "application/pdf"


def extract_text_from_image(file_bytes: bytes) -> str:
    """OCR a single PNG/JPEG image with Tesseract."""
    with Image.open(io.BytesIO(file_bytes)) as img:
        return pytesseract.image_to_string(img.convert("RGB"))


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