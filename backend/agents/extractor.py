"""Agent 2: pydantic-ai structured field extraction (amounts, dates, parties)."""

from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent

from backend.core.config import settings
from backend.core.token_budget import (
    estimate_tokens,
    get_budget_for_model,
    reserve_or_raise,
)
from backend.plugins.base import DocumentPlugin


async def extract_fields(
    raw_text: str,
    plugin: DocumentPlugin,
    model: Any,
    redis_client: Any = None,
) -> BaseModel:
    """
    Dynamically creates an agent using the plugin's schema + prompt,
    runs it against the raw text, and returns structured output.

    Args:
        raw_text: Raw text extracted from the document.
        plugin: Document plugin with extraction schema and prompt.
        model: pydantic-ai model instance, resolved by the pipeline (server
            key, or a caller-supplied key when that is enabled).
        redis_client: When given, reserves capacity against ADR 006's token
            budget before calling the model and settles it against the real
            usage afterward. `None` (the default, used by unit tests with
            TestModel/FunctionModel) skips budgeting entirely — there is no
            real capacity to protect against a fake model.

    Raises:
        backend.core.token_budget.CapacityWaitError: no room in the budget
            right now. The caller (the pipeline, via the worker) turns this
            into a deferred retry rather than a failed document.
    """

    model_name = getattr(model, "model_name", str(model))
    reservation = None
    if redis_client is not None:
        messages = [
            {"role": "system", "content": plugin.system_prompt},
            {"role": "user", "content": raw_text},
        ]
        estimated = estimate_tokens(messages, settings.llm_max_completion_tokens)
        reservation = reserve_or_raise(redis_client, model_name, estimated)

    agent = Agent(
        model=model,
        output_type=plugin.extraction_schema,
        system_prompt=plugin.system_prompt,
    )

    result = await agent.run(
        raw_text,
        model_settings={"max_tokens": settings.llm_max_completion_tokens},
    )

    if reservation is not None:
        usage = result.usage
        actual = (usage.input_tokens or 0) + (usage.output_tokens or 0)
        get_budget_for_model(redis_client, model_name).settle(reservation, actual)

    return result.output
