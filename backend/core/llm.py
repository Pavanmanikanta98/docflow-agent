"""
LLMClient abstraction — the only place in the codebase that touches LLM SDKs.
Switch providers via LLM_PROVIDER env variable. Zero business-logic changes required.
"""

from typing import Any

from backend.core.config import settings


class LLMClient:
    """Thin wrapper that returns a pydantic-ai-compatible model object.

    Usage:
        client = LLMClient()
        model = client.get_model()
        # Pass `model` to any pydantic-ai Agent constructor.
    """

    def get_model(self) -> Any:
        """Return the configured pydantic-ai model instance."""
        provider = settings.llm_provider.lower()

        if provider == "groq":
            return self._groq_model()
        if provider == "ollama":
            return self._ollama_model()
        if provider == "openai":
            return self._openai_model()

        raise ValueError(
            f"Unknown LLM_PROVIDER: {provider!r}. "
            "Valid values: groq | ollama | openai"
        )

    def _groq_model(self) -> Any:
        import os
        from pydantic_ai.models.groq import GroqModel
        os.environ["GROQ_API_KEY"] = settings.groq_api_key   # Inject before constructing
        return GroqModel(settings.llm_model)

    def _ollama_model(self) -> Any:
        from pydantic_ai.models.ollama import OllamaModel

        return OllamaModel(settings.llm_model)

    def _openai_model(self) -> Any:
        from pydantic_ai.models.openai import OpenAIModel

        return OpenAIModel(settings.llm_model)


llm_client = LLMClient()
