"""Shared fixtures and deterministic metrics for the evaluation suite.

WHY DETERMINISTIC METRICS?
─────────────────────────
DeepEval supports "LLM-as-judge" metrics (GEval) where a second LLM
grades the output. That's powerful but:
  1. Doubles API cost (one call to extract, one call to judge)
  2. Non-deterministic — the judge LLM can change its mind between runs
  3. Overkill for field-level extraction where we have known correct answers

Instead we use DETERMINISTIC metrics:
  - Exact match:   total_amount == 715.00        (numbers, dates, booleans)
  - Fuzzy match:    "Acme Corp" ≈ "ACME Corp."   (names, free-text)
  - Presence check: invoice_number is not None    (field was extracted at all)
  - List overlap:   3 of 5 line items matched     (list fields)

These are cheaper, reproducible, and easier to debug.
"""

import json
import math
from pathlib import Path
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

GOLDEN_DIR = Path(__file__).parent / "golden"


def load_golden(filename: str) -> list[dict]:
    """Load a gold-standard dataset from the golden/ directory."""
    path = GOLDEN_DIR / filename
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Deterministic Metrics
# ---------------------------------------------------------------------------

def fuzzy_match(actual: str | None, expected: str | None, threshold: float = 0.75) -> bool:
    """Check if two strings are similar enough using SequenceMatcher.

    WHY THIS AND NOT ==?
    LLMs return slight variations: "Acme Corp" vs "Acme Corp."
    SequenceMatcher handles these without regex or normalization.

    Args:
        actual: The LLM's output string.
        expected: The gold-standard string.
        threshold: Minimum similarity ratio (0.0–1.0). Default 0.75.

    Returns:
        True if the strings are similar enough.
    """
    if actual is None and expected is None:
        return True
    if actual is None or expected is None:
        return False

    # Normalize: lowercase, strip whitespace
    a = actual.strip().lower()
    e = expected.strip().lower()

    ratio = SequenceMatcher(None, a, e).ratio()
    return ratio >= threshold


def exact_match_number(
    actual: float | int | None,
    expected: float | int | None,
    tolerance: float = 0.01,
) -> bool:
    """Check if two numbers match within a tolerance.

    WHY TOLERANCE?
    LLMs sometimes return 714.99 instead of 715.00 due to
    floating-point parsing of comma-formatted numbers.

    Args:
        actual: The LLM's extracted number.
        expected: The gold-standard number.
        tolerance: Acceptable absolute difference.
    """
    if actual is None and expected is None:
        return True
    if actual is None or expected is None:
        return False
    return math.isclose(actual, expected, abs_tol=tolerance)


def date_match(actual: str | None, expected: str | None) -> bool:
    """Check if two date strings represent the same date.

    WHY THIS AND NOT fuzzy_match FOR DATES?
    LLMs return dates in wildly different formats:
      "April 20, 2026" vs "2026-04-20" vs "20/04/2026"
    These look nothing alike as strings but are the same date.
    We parse both into date objects and compare directly.

    Falls back to fuzzy_match if parsing fails.
    """
    if actual is None and expected is None:
        return True
    if actual is None or expected is None:
        return False

    # Common date formats LLMs produce
    formats = [
        "%Y-%m-%d",          # 2026-04-20
        "%m/%d/%Y",          # 04/20/2026
        "%d/%m/%Y",          # 20/04/2026
        "%Y/%m/%d",          # 2026/04/20
        "%d-%m-%Y",          # 20-04-2026
        "%B %d, %Y",         # April 20, 2026
        "%b %d, %Y",         # Apr 20, 2026
        "%d %B %Y",          # 20 April 2026
        "%d %b %Y",          # 20 Apr 2026
        "%d-%b-%Y",          # 20-Apr-2026
        "%d.%m.%Y",          # 20.04.2026
        "%B %d %Y",          # April 20 2026
        "%d %B, %Y",         # 20 April, 2026
    ]

    def try_parse(s: str) -> datetime | None:
        s = s.strip()
        for fmt in formats:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None

    parsed_actual = try_parse(actual)
    parsed_expected = try_parse(expected)

    if parsed_actual and parsed_expected:
        return parsed_actual.date() == parsed_expected.date()

    # Fallback: fuzzy string comparison
    return fuzzy_match(actual, expected, threshold=0.75)


def null_match(actual: Any, expected: Any) -> bool:
    """Check that both are null or both are non-null.

    WHY THIS EXISTS:
    If a field truly doesn't exist in the document (e.g. no due_date),
    the LLM should return null — not make one up. This catches
    hallucinated values.
    """
    return (actual is None) == (expected is None)


def list_overlap_score(
    actual: list[str] | None,
    expected: list[str] | None,
    threshold: float = 0.6,
) -> float:
    """Calculate what fraction of expected list items were found in actual.

    WHY OVERLAP AND NOT EXACT?
    Line items are messy — the LLM might reformat "Widget A  x10  $50.00"
    as "Widget A x10 $50.00". We fuzzy-match each expected item against
    all actual items and count hits.

    Returns:
        0.0 to 1.0 — fraction of expected items found.
    """
    if actual is None and expected is None:
        return 1.0
    if actual is None or expected is None:
        return 0.0
    if len(expected) == 0:
        return 1.0

    hits = 0
    for exp_item in expected:
        for act_item in actual:
            if fuzzy_match(act_item, exp_item, threshold=threshold):
                hits += 1
                break

    return hits / len(expected)


# ---------------------------------------------------------------------------
# Per-Case Evaluation Result
# ---------------------------------------------------------------------------

@dataclass
class FieldResult:
    """Result of evaluating a single field."""
    field_name: str
    passed: bool
    actual: Any = None
    expected: Any = None
    detail: str = ""


@dataclass
class CaseResult:
    """Result of evaluating a single test case (one document)."""
    case_id: str
    description: str
    field_results: list[FieldResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        """Fraction of fields that passed (0.0–1.0)."""
        if not self.field_results:
            return 0.0
        passed = sum(1 for r in self.field_results if r.passed)
        return passed / len(self.field_results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.field_results if r.passed)

    @property
    def total_count(self) -> int:
        return len(self.field_results)

    def summary(self) -> str:
        """Human-readable summary for test output."""
        lines = [f"\n{'='*60}"]
        lines.append(f"Case: {self.case_id}")
        lines.append(f"  {self.description}")
        lines.append(f"  Accuracy: {self.accuracy:.0%} ({self.passed_count}/{self.total_count})")
        for r in self.field_results:
            icon = "✅" if r.passed else "❌"
            lines.append(f"  {icon} {r.field_name}: {r.detail}")
        return "\n".join(lines)
