"""ADR 007 — a tiny, dependency-free character error rate.

The CI guard (backend/tests/unit/test_ocr_cer_guard.py) must run without
the "eval" extra (jiwer) installed — CI only does `uv sync --extra dev`, and
jiwer stays out of that on purpose, same as deepeval (ADR 008). This is not
a replacement for jiwer: the full evaluation script
(backend/tests/evaluation/run_ocr_eval.py) uses jiwer directly for both CER
and WER. This module exists only so the CI guard has zero extra
dependencies to compute the one metric it needs.
"""

from __future__ import annotations


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein edit distance divided by the reference length.

    An empty reference with a non-empty hypothesis is defined as CER 1.0
    (completely wrong, since anything produced is an insertion against
    nothing); an empty reference with an empty hypothesis is CER 0.0.
    """
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return _levenshtein(reference, hypothesis) / len(reference)


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous_row = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current_row = [i]
        for j, char_b in enumerate(b, start=1):
            insert_cost = current_row[j - 1] + 1
            delete_cost = previous_row[j] + 1
            substitute_cost = previous_row[j - 1] + (char_a != char_b)
            current_row.append(min(insert_cost, delete_cost, substitute_cost))
        previous_row = current_row
    return previous_row[-1]
