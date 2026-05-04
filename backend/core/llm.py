"""
LLMClient abstraction — the only place in the codebase that touches LLM SDKs.

Supports two modes:
  1. Global fallback: reads LLM_PROVIDER + GROQ_API_KEY from .env (demo mode).
  2. Per-tenant BYOK: caller passes provider, api_key, and model explicitly.
"""

from typing import Any

from backend.core.config import settings


class LLMClient:
    """Thin wrapper that returns a pydantic-ai-compatible model object.

    Usage (global fallback):
        client = LLMClient()
        model = client.get_model()

    Usage (per-tenant BYOK):
        model = client.get_model(provider="groq", api_key="gsk_...", model_name="llama-3.1-8b-instant")
    """

    def get_model(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> Any:
        """Return the configured pydantic-ai model instance.

        When called with no arguments, falls back to .env defaults.
        When called with explicit overrides, uses the tenant's BYOK key.
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
        import os
        from pydantic_ai.models.groq import GroqModel

        # Inject into env — pydantic-ai reads GROQ_API_KEY from os.environ
        key = api_key or settings.groq_api_key
        if key:
            os.environ["GROQ_API_KEY"] = key
        return GroqModel(model_name)

    def _ollama_model(self, model_name: str) -> Any:
        from pydantic_ai.models.ollama import OllamaModel

        return OllamaModel(model_name)

    def _openai_model(self, model_name: str, api_key: str | None = None) -> Any:
        import os
        from pydantic_ai.models.openai import OpenAIModel

        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        return OpenAIModel(model_name)


llm_client = LLMClient()
