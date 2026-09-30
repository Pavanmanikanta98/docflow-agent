"""ADR 007 — CI guard: OCR character error rate on 3 fixed synthetic
images must not regress. No LLM call, no network, no "eval" extra (jiwer)
required — see backend/core/ocr_metrics.py for why.

Thresholds are the measured baseline (Tesseract 5.3.4, default PSM, on
this repo's dev container) plus a stated margin, not an arbitrary number —
a Tesseract upgrade or a real regression in backend/agents/parser.py's OCR
path is expected to be caught here, per-variant, not blurred into one
average.
"""

import shutil

import pytesseract
import pytest

from backend.core.ocr_metrics import character_error_rate
from backend.core.ocr_synthetic import make_variant

requires_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="tesseract binary not installed (apt-get install tesseract-ocr)",
)

# (text, variant, measured_baseline_cer, margin) — baseline measured once
# against Tesseract 5.3.4 with PyMuPDF's page rendering at each variant's
# DPI; margin absorbs minor cross-machine Tesseract/rendering differences
# without hiding a real regression.
CASES = [
    (
        "INVOICE #INV-2026-0042\nDate: 2026-04-15\nFrom: Acme Corp\nTotal: $715.00",
        "dpi_150",
        0.0429,
        0.05,
    ),
    (
        "Invoice Number: 88921\nInvoice Date: March 3, 2026\nTotal Due: EUR 2450.00",
        "blurred",
        0.0139,
        0.05,
    ),
    (
        "COMMERCIAL INVOICE\nRef: CI-2026/1107\nSubtotal: $26450.00\nTotal: $26850.00",
        "jpeg_q40",
        0.0274,
        0.05,
    ),
]


@requires_tesseract
@pytest.mark.parametrize("text,variant,baseline_cer,margin", CASES)
def test_ocr_cer_does_not_regress(text, variant, baseline_cer, margin):
    image = make_variant(text, variant)
    ocr_text = pytesseract.image_to_string(image)

    cer = character_error_rate(text, ocr_text)

    assert cer <= baseline_cer + margin, (
        f"{variant}: CER {cer:.4f} exceeds the measured baseline "
        f"{baseline_cer:.4f} + margin {margin:.2f} — Tesseract's OCR "
        f"accuracy on this variant regressed"
    )
