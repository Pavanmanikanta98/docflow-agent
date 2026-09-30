"""ADR 007 — the dependency-free CER used by the CI guard."""

import pytest

from backend.core.ocr_metrics import character_error_rate


def test_identical_strings_have_zero_cer():
    assert character_error_rate("hello world", "hello world") == 0.0


def test_completely_different_strings_have_high_cer():
    assert character_error_rate("abc", "xyz") == pytest.approx(1.0)


def test_one_substitution_out_of_five_chars():
    assert character_error_rate("hello", "hallo") == pytest.approx(0.2)


def test_empty_reference_and_empty_hypothesis_is_zero():
    assert character_error_rate("", "") == 0.0


def test_empty_reference_with_nonempty_hypothesis_is_one():
    assert character_error_rate("", "garbage") == 1.0


def test_insertions_count_toward_cer():
    assert character_error_rate("cat", "caterpillar") == pytest.approx(8 / 3)
