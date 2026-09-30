"""ADR 006 — pricing math is a pure function, verified against the live
Groq models API on 2026-09-24 (see backend/core/pricing.py's docstring)."""

import pytest

from backend.core.pricing import BATCH_DISCOUNT, MODEL_PRICING, get_pricing


def test_known_models_are_priced():
    assert "openai/gpt-oss-20b" in MODEL_PRICING
    assert "openai/gpt-oss-120b" in MODEL_PRICING


def test_prices_match_the_verified_live_values():
    twenty_b = get_pricing("openai/gpt-oss-20b")
    assert twenty_b.input_price_per_1m == pytest.approx(0.075)
    assert twenty_b.output_price_per_1m == pytest.approx(0.30)

    hundred_twenty_b = get_pricing("openai/gpt-oss-120b")
    assert hundred_twenty_b.input_price_per_1m == pytest.approx(0.15)
    assert hundred_twenty_b.output_price_per_1m == pytest.approx(0.60)


def test_unknown_model_raises_rather_than_guessing():
    with pytest.raises(KeyError):
        get_pricing("some-model-nobody-priced")


def test_cost_scales_linearly_with_tokens():
    pricing = get_pricing("openai/gpt-oss-20b")
    one_million_in = pricing.cost(input_tokens=1_000_000, output_tokens=0)
    assert one_million_in == pytest.approx(0.075)

    one_million_out = pricing.cost(input_tokens=0, output_tokens=1_000_000)
    assert one_million_out == pytest.approx(0.30)


def test_batch_applies_the_configured_discount():
    pricing = get_pricing("openai/gpt-oss-120b")
    standard = pricing.cost(input_tokens=1000, output_tokens=1000, batch=False)
    batch = pricing.cost(input_tokens=1000, output_tokens=1000, batch=True)
    assert batch == pytest.approx(standard * (1 - BATCH_DISCOUNT))
