"""Agent 2: pydantic-ai structured field extraction (amounts, dates, parties)."""

from typing import Any
from pydantic import BaseModel
from pydantic_ai import Agent
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
        model: pydantic-ai model instance (resolved by pipeline — tenant BYOK or fallback).
    """

    agent = Agent(
        model=model,
        output_type=plugin.extraction_schema,
        system_prompt=plugin.system_prompt,
    )

    result = await agent.run(raw_text)
    return result.output
