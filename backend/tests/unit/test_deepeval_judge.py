"""Unit tests for the DeepEval judge wrapper (LLMClientBasedJudge).

Tests verify:
- get_model_name() returns the configured model
- a_generate() calls through LLMClient correctly
- generate() wraps a_generate
- temperature 0 is passed to the model
- Token budget reserve/settle are called when redis_client is provided
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.core.deepeval_judge import LLMClientBasedJudge


@pytest.mark.asyncio
async def test_get_model_name_returns_configured_model() -> None:
    """Verify get_model_name() returns the judge model name."""
    judge = LLMClientBasedJudge(model_name="openai/gpt-oss-120b")
    assert judge.get_model_name() == "openai/gpt-oss-120b"


@pytest.mark.asyncio
async def test_load_model_is_noop() -> None:
    """load_model() is a no-op (model is built lazily in generate)."""
    judge = LLMClientBasedJudge()
    judge.load_model()  # Should not raise


def test_generate_wraps_async() -> None:
    """generate() (sync) successfully wraps a_generate()."""
    judge = LLMClientBasedJudge()

    async def mock_async_gen(prompt: str) -> str:
        return "mocked response"

    judge.a_generate = mock_async_gen

    result = judge.generate("test prompt")
    assert result == "mocked response"


@pytest.mark.asyncio
async def test_a_generate_calls_llm_client_with_temperature_zero() -> None:
    """a_generate() builds an Agent via LLMClient and passes temperature=0."""
    judge = LLMClientBasedJudge(model_name="openai/gpt-oss-120b")

    # Mock the Agent.run method to capture model_settings
    with patch("pydantic_ai.Agent") as mock_agent_class:
        mock_agent = AsyncMock()
        mock_agent_class.return_value = mock_agent

        # Mock result with usage
        mock_result = Mock()
        mock_result.output = "judge response"
        mock_result.usage = Mock(input_tokens=10, output_tokens=5)
        mock_agent.run.return_value = mock_result

        # Mock LLMClient.get_model
        with patch(
            "backend.core.deepeval_judge.llm_client.get_model"
        ) as mock_get_model:
            mock_model = Mock()
            mock_get_model.return_value = mock_model

            result = await judge.a_generate("test prompt")

            # Verify Agent was created with the mock model
            mock_agent_class.assert_called_once_with(model=mock_model)

            # Verify Agent.run was called with temperature=0
            mock_agent.run.assert_called_once()
            call_kwargs = mock_agent.run.call_args[1]
            assert call_kwargs["model_settings"]["temperature"] == 0

            # Verify the response is returned
            assert result == "judge response"


@pytest.mark.asyncio
async def test_a_generate_without_redis_skips_budget() -> None:
    """When redis_client is None, token budget is skipped."""
    judge = LLMClientBasedJudge(redis_client=None)

    with patch("pydantic_ai.Agent") as mock_agent_class:
        mock_agent = AsyncMock()
        mock_agent_class.return_value = mock_agent

        mock_result = Mock()
        mock_result.output = "response"
        mock_result.usage = Mock(input_tokens=10, output_tokens=5)
        mock_agent.run.return_value = mock_result

        with patch("backend.core.deepeval_judge.llm_client.get_model"):
            with patch(
                "backend.core.deepeval_judge.reserve_or_raise"
            ) as mock_reserve:
                result = await judge.a_generate("test prompt")

                # reserve_or_raise should NOT have been called
                mock_reserve.assert_not_called()
                assert result == "response"


@pytest.mark.asyncio
async def test_a_generate_with_redis_reserves_and_settles() -> None:
    """When redis_client is set, token budget reserve/settle are called."""
    mock_redis = Mock()
    judge = LLMClientBasedJudge(redis_client=mock_redis)

    with patch("pydantic_ai.Agent") as mock_agent_class:
        mock_agent = AsyncMock()
        mock_agent_class.return_value = mock_agent

        mock_result = Mock()
        mock_result.output = "response"
        mock_result.usage = Mock(input_tokens=100, output_tokens=50)
        mock_agent.run.return_value = mock_result

        with patch(
            "backend.core.deepeval_judge.estimate_tokens"
        ) as mock_estimate:
            mock_estimate.return_value = 1500

            with patch(
                "backend.core.deepeval_judge.llm_client.get_model"
            ) as mock_get_model:
                mock_model = Mock()
                mock_get_model.return_value = mock_model

                with patch(
                    "backend.core.deepeval_judge.reserve_or_raise"
                ) as mock_reserve:
                    mock_reservation = Mock()
                    mock_reserve.return_value = mock_reservation

                    with patch(
                        "backend.core.deepeval_judge.get_budget_for_model"
                    ) as mock_get_budget:
                        mock_budget = Mock()
                        mock_get_budget.return_value = mock_budget

                        result = await judge.a_generate("test prompt")

                        # reserve_or_raise should have been called
                        mock_reserve.assert_called_once()
                        reserve_args = mock_reserve.call_args[0]
                        assert reserve_args[0] == mock_redis
                        assert reserve_args[1] == "openai/gpt-oss-120b"

                        # settle should have been called with actual tokens
                        mock_budget.settle.assert_called_once()
                        settle_args = mock_budget.settle.call_args[0]
                        assert settle_args[0] == mock_reservation
                        assert settle_args[1] == 150  # 100 input + 50 output

                        assert result == "response"


@pytest.mark.asyncio
async def test_a_generate_default_model_name() -> None:
    """When model_name is not provided, defaults to gpt-oss-120b."""
    judge = LLMClientBasedJudge()
    assert judge.get_model_name() == "openai/gpt-oss-120b"
