"""Agent 2: pydantic-ai structured field extraction (amounts, dates, parties)."""

from typing import Optional
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from backend.core.llm import llm_client
from backend.plugins.base import DocumentPlugin


async def extract_fields(raw_text: str, plugin: DocumentPlugin) -> BaseModel:
    """
    Dynamically creates an agent using the plugin's schema + prompt,
    runs it against the raw text, and returns structured output.
    """

    agent = Agent(
        model=llm_client.get_model(),
        output_type=plugin.extraction_schema,
        system_prompt=plugin.system_prompt,
    )

    result = await agent.run(raw_text)
    return result.output
