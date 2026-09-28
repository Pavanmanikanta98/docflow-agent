"""Agent 2: pydantic-ai structured field extraction (amounts, dates, parties)."""

from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.usage import RunUsage

from backend.plugins.base import DocumentPlugin


async def extract_fields(
    raw_text: str,
    plugin: DocumentPlugin,
    model: Any,
) -> BaseModel:
    """
    Dynamically creates an agent using the plugin's schema + prompt,
    runs it against the raw text, and returns structured output.

    Args:
        raw_text: Raw text extracted from the document.
        plugin: Document plugin with extraction schema and prompt.
        model: pydantic-ai model instance, resolved by the pipeline (server
            key, or a caller-supplied key when that is enabled).
    """
    fields, _ = await extract_fields_with_usage(raw_text, plugin, model)
    return fields


async def extract_fields_with_usage(
    raw_text: str,
    plugin: DocumentPlugin,
    model: Any,
) -> tuple[BaseModel, RunUsage]:
    """
    Extract structured fields and return usage info (tokens, cost).

    Args:
        raw_text: Raw text extracted from the document.
        plugin: Document plugin with extraction schema and prompt.
        model: pydantic-ai model instance.

    Returns:
        (fields, usage) where fields is the extraction schema instance
        and usage is pydantic-ai's RunUsage object with token counts.
    """
    agent = Agent(
        model=model,
        output_type=plugin.extraction_schema,
        system_prompt=plugin.system_prompt,
    )

    result = await agent.run(raw_text)
    return result.output, result.usage
