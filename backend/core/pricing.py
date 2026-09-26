"""ADR 006 — the cost model: per-model token prices and the batch discount.

Prices are config, not a guess: every number here carries the source it
was checked against and the date it was checked, because a hosted model's
price (like its availability — see ADR 005) is not something this repo
controls or can assume stays fixed.

Verified live on 2026-09-24 against `GET https://api.groq.com/openai/v1/models`,
which returns each model's own billing metadata (`pricing.prompt` and
`pricing.completion`, in $ per token):

    openai/gpt-oss-20b:  prompt 0.000000075 ($0.075/1M), completion 0.0000003 ($0.30/1M)
    openai/gpt-oss-120b: prompt 0.00000015  ($0.15/1M),  completion 0.0000006 ($0.60/1M)

These match the numbers this session was given, confirmed against the
actual billing source rather than a marketing page (console.groq.com and
groq.com are both outside this session's network policy; the models API
itself was not).

The batch discount (50% off standard, on-demand rates) is Groq's published
batch pricing. It is NOT independently re-verified against a live billing
response here: exercising the real Batch API needs the paid Developer
tier, which this free-tier-only session does not have (see
`scripts/bulk_submit.py`, built and tested against mocked HTTP only).
"""

from __future__ import annotations

from dataclasses import dataclass

PRICING_SOURCE_URL = "https://api.groq.com/openai/v1/models"
PRICING_CHECKED_DATE = "2026-09-24"

BATCH_DISCOUNT = 0.5  # 50% off standard rates — Groq's published batch pricing.
BATCH_DISCOUNT_SOURCE = (
    "Groq's published Batch API pricing (50% off on-demand rates); not "
    "independently re-verified live — the Batch API requires the paid "
    "Developer tier (see scripts/bulk_submit.py)."
)


@dataclass(frozen=True)
class ModelPricing:
    model: str
    input_price_per_1m: float
    output_price_per_1m: float

    def cost(self, input_tokens: int, output_tokens: int, batch: bool = False) -> float:
        """Cost in USD for a given token count, optionally at the batch rate."""
        discount = BATCH_DISCOUNT if batch else 0.0
        input_cost = (input_tokens / 1_000_000) * self.input_price_per_1m
        output_cost = (output_tokens / 1_000_000) * self.output_price_per_1m
        return (input_cost + output_cost) * (1 - discount)


# Verified live against PRICING_SOURCE_URL on PRICING_CHECKED_DATE (see module
# docstring). Re-check before trusting these for a number that will be
# published — a hosted model's price is not guaranteed to stay fixed.
MODEL_PRICING: dict[str, ModelPricing] = {
    "openai/gpt-oss-20b": ModelPricing(
        model="openai/gpt-oss-20b", input_price_per_1m=0.075, output_price_per_1m=0.30
    ),
    "openai/gpt-oss-120b": ModelPricing(
        model="openai/gpt-oss-120b", input_price_per_1m=0.15, output_price_per_1m=0.60
    ),
}


def get_pricing(model: str) -> ModelPricing:
    """Raises KeyError for a model this cost model does not have prices for —
    deliberately no silent fallback, since a wrong price is worse than none."""
    return MODEL_PRICING[model]
