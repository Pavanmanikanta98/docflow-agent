"""
LLMClient abstraction — the only place in the codebase that touches LLM SDKs.

Supports two modes:
  1. Server key (the default): reads LLM_PROVIDER + GROQ_API_KEY from .env.
  2. Explicit override: the caller passes provider, api_key and model. Kept
     for provider-swap flexibility; nothing in the request path uses it
     since ADR 003 removed the caller-supplied key.

Every model built here carries an httpx response hook (ADR 006) that syncs
`backend.core.token_budget` from the provider's `x-ratelimit-*` headers on
every call, and sets the shared capacity cooldown on a 429 — so the token
budget's view of remaining capacity self-corrects from the real API, not
just from our own request-size estimates.
"""

from typing import Any

import httpx

from backend.core.config import settings


class LLMClient:
    """Thin wrapper that returns a pydantic-ai-compatible model object.

    Usage (server key):
        client = LLMClient()
        model = client.get_model()

    Usage (explicit override):
        model = client.get_model(
            provider="groq", api_key="gsk_...", model_name="openai/gpt-oss-20b"
        )
    """

    def get_model(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> Any:
        """Return the configured pydantic-ai model instance.

        With no arguments, uses the .env defaults. With explicit arguments,
        uses the key, provider and model passed in — the key reaches this
        model's provider only, never os.environ.
        """
        resolved_provider = (provider or settings.llm_provider).lower()
        resolved_model = model_name or settings.llm_model
        resolved_key = api_key  # None means use the env default inside each builder

        if resolved_provider == "groq":
            return self._groq_model(resolved_model, resolved_key)
        if resolved_provider == "ollama":
            return self._ollama_model(resolved_model)
        if resolved_provider == "openai":
            return self._openai_model(resolved_model, resolved_key)

        raise ValueError(
            f"Unknown LLM_PROVIDER: {resolved_provider!r}. "
            "Valid values: groq | ollama | openai"
        )

    def _groq_model(self, model_name: str, api_key: str | None = None) -> Any:
        from pydantic_ai.models.groq import GroqModel
        from pydantic_ai.providers.groq import GroqProvider

        # Pass the key to this model's provider only. Writing it into os.environ
        # would make it process-wide and visible to every later request.
        key = api_key or settings.groq_api_key
        http_client = _http_client_with_capacity_hook(model_name)
        base_url = settings.groq_base_url or None
        if key:
            return GroqModel(
                model_name,
                provider=GroqProvider(
                    api_key=key, base_url=base_url, http_client=http_client
                ),
            )
        return GroqModel(
            model_name,
            provider=GroqProvider(base_url=base_url, http_client=http_client),
        )

    def _ollama_model(self, model_name: str) -> Any:
        from pydantic_ai.models.ollama import OllamaModel

        return OllamaModel(model_name)

    def _openai_model(self, model_name: str, api_key: str | None = None) -> Any:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        key = api_key or settings.openai_api_key
        http_client = _http_client_with_capacity_hook(model_name)
        if key:
            return OpenAIChatModel(
                model_name,
                provider=OpenAIProvider(api_key=key, http_client=http_client),
            )
        return OpenAIChatModel(
            model_name, provider=OpenAIProvider(http_client=http_client)
        )


def _http_client_with_capacity_hook(model_name: str) -> httpx.AsyncClient:
    """An httpx client whose response hook feeds ADR 006's token budget.

    A fresh client per model build matches this module's existing pattern of
    building a fresh provider/model per call (see `LLMClient.get_model`) —
    it is not a new resource-lifetime concern this change introduces.
    """

    async def _sync_budget_from_response(response: httpx.Response) -> None:
        from backend.core.db import redis_client
        from backend.core.token_budget import get_budget_for_model

        budget = get_budget_for_model(redis_client, model_name)
        budget.sync_from_headers(response.headers)
        if response.status_code == 429:
            budget.set_cooldown_from_retry_after(response.headers)

    return httpx.AsyncClient(event_hooks={"response": [_sync_budget_from_response]})


llm_client = LLMClient()
