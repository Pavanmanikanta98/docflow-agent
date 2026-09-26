"""DeepEval GEval judge wrapping LLMClient for contract free-text evaluation.

The judge is a deliberately different model (`gpt-oss-120b`) from the
extractor, with temperature 0, and every call goes through ADR 006's token
bucket — avoiding self-grading bias and respecting shared free-tier capacity.

This module defines a DeepEvalBaseLLM subclass that pydantic-ai's Agent
(inside LLMClient) can use as its underlying model, without building a
separate LLM-calling code path. Temperature 0 and token budget are enforced
at call time.
"""

import asyncio
from typing import Any, Optional

from deepeval.models import DeepEvalBaseLLM

from backend.core.llm import llm_client
from backend.core.token_budget import (
    estimate_tokens,
    get_budget_for_model,
    reserve_or_raise,
)


class LLMClientBasedJudge(DeepEvalBaseLLM):
    """A DeepEvalBaseLLM wrapping LLMClient + pydantic-ai Agent.

    Used by DeepEval's GEval metric to judge contract free-text fields
    (`termination_clause`, `key_obligations`). The judge model is always
    `gpt-oss-120b` (a deliberately larger model than the extractor).

    When `redis_client` is passed, all calls reserve capacity against the
    token budget and settle the real usage afterward, exactly like
    `extract_fields` does. Without a redis_client, token budgeting is
    skipped (used by unit tests with FunctionModel/TestModel).
    """

    def __init__(
        self,
        model_name: str = "openai/gpt-oss-120b",
        redis_client: Optional[Any] = None,
    ) -> None:
        """Initialize the judge.

        Args:
            model_name: The LLM to use for judging. Defaults to gpt-oss-120b
                (a larger model than the extractor, to avoid self-grading bias).
            redis_client: Optional Redis client for token budget tracking.
                When provided, judge calls respect the ADR 006 token bucket.
                When None, no budgeting is done (unit tests only).
        """
        super().__init__()
        self.model_name = model_name
        self.redis_client = redis_client

    def load_model(self) -> None:
        """Load the model.

        For our wrapper, this is a no-op — the pydantic-ai Agent is built
        lazily in generate/a_generate when needed. This satisfies the
        abstract method contract.
        """
        pass

    def get_model_name(self) -> str:
        """Return the model name this judge uses."""
        return self.model_name

    def generate(self, prompt: str) -> str:
        """Synchronous generate — calls the async version via asyncio.run."""
        try:
            asyncio.get_running_loop()
            # If we're already in an async context, we can't use asyncio.run
            # Fall back to creating a new thread for the coroutine
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, self.a_generate(prompt))
                return future.result()
        except RuntimeError:
            # No running event loop, safe to use asyncio.run
            return asyncio.run(self.a_generate(prompt))

    async def a_generate(self, prompt: str) -> str:
        """Asynchronous generate using LLMClient + Agent.

        Builds an agent with temperature 0, reserves capacity if redis_client
        is present, runs the prompt, settles the budget, and returns the
        generated text.

        Args:
            prompt: The prompt to generate a response for.

        Returns:
            The model's generated text.

        Raises:
            backend.core.token_budget.CapacityWaitError: If redis_client is
                set and no capacity is available right now.
        """
        from pydantic_ai import Agent

        # Build the model with temperature 0
        model = llm_client.get_model(model_name=self.model_name)

        # Estimate and reserve capacity if redis_client is set
        reservation = None
        if self.redis_client is not None:
            messages = [{"role": "user", "content": prompt}]
            # Estimate: prompt + a reasonable completion budget (1000 tokens)
            estimated = estimate_tokens(messages, max_completion_tokens=1000)
            reservation = reserve_or_raise(
                self.redis_client, self.model_name, estimated
            )

        # Create a minimal agent that just echoes the prompt as system context
        # and returns the generated response
        agent = Agent(model=model)

        # Run with temperature 0
        result = await agent.run(
            prompt,
            model_settings={"temperature": 0, "max_tokens": 1000},
        )

        # Settle the budget with actual usage
        if reservation is not None:
            usage = result.usage
            actual = (usage.input_tokens or 0) + (usage.output_tokens or 0)
            get_budget_for_model(self.redis_client, self.model_name).settle(
                reservation, actual
            )

        return result.output
