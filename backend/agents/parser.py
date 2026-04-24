"""Agent 1: extract raw text from document.

3-tier fallback strategy:
  1. PyMuPDF  — fast, handles digital PDFs
  2. pdfplumber — catches edge cases PyMuPDF misses
  3. Tesseract OCR — handles scanned/image-based PDFs

Returns the first non-empty result. If all three fail, returns "".
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
    Main entry point. Tries 3 extraction methods in order.
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