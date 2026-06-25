"""Tests for LLM multi-provider module.

Tests cover:
- Provider client creation (AC-1)
- Fallback logic with 5xx/4xx differentiation (AC-3)
- DeepSeek down → Doubao success scenario (AC-4)
- Token telemetry (AC-5)
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import Request
from openai import APIConnectionError, APIStatusError

from app.llm_multi_provider import (
    AllProvidersFailedError,
    DEFAULT_FALLBACK_ORDER,
    LLMResponse,
    LLMUsage,
    ProviderConfigError,
    call_llm_single,
    call_llm_with_fallback,
    get_async_client,
    get_client,
    _is_retryable_error,
)


# === AC-1: get_client() returns (OpenAI, model) tuple ===


class TestGetClient:
    """Tests for get_client() function."""

    def test_get_client_deepseek_returns_tuple(self):
        """AC-1: get_client returns OpenAI instance and model name."""
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_MODEL": "deepseek-chat"},
        ):
            client, model = get_client("deepseek")
            assert client is not None
            assert model == "deepseek-chat"

    def test_get_client_doubao_uses_endpoint_id(self):
        """Doubao uses endpoint ID (ARK_MODEL_ENDPOINT_ID), not model name."""
        with patch.dict(
            os.environ,
            {"ARK_API_KEY": "test-key", "ARK_MODEL_ENDPOINT_ID": "ep-2024xxxx"},
        ):
            client, model = get_client("doubao")
            assert client is not None
            assert model == "ep-2024xxxx"

    def test_get_client_qwen_returns_tuple(self):
        """AC-1: Qwen provider configuration."""
        with patch.dict(
            os.environ,
            {"DASHSCOPE_API_KEY": "test-key", "QWEN_MODEL": "qwen-plus"},
        ):
            client, model = get_client("qwen")
            assert client is not None
            assert model == "qwen-plus"

    def test_get_client_minimax_returns_tuple(self):
        """AC-1: MiniMax provider configuration."""
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "test-key", "MINIMAX_MODEL": "abab6.5s-chat"},
        ):
            client, model = get_client("minimax")
            assert client is not None
            assert model == "abab6.5s-chat"

    def test_get_client_unknown_provider_raises(self):
        """Unknown provider should raise ProviderConfigError."""
        with pytest.raises(ProviderConfigError) as exc_info:
            get_client("unknown_provider")
        assert "Unknown provider" in str(exc_info.value)

    def test_get_client_missing_api_key_raises(self):
        """Missing API key should raise ProviderConfigError."""
        # Clear all API keys
        env_backup = os.environ.copy()
        for key in ["DEEPSEEK_API_KEY", "ARK_API_KEY", "DASHSCOPE_API_KEY", "MINIMAX_API_KEY"]:
            os.environ.pop(key, None)

        try:
            with pytest.raises(ProviderConfigError) as exc_info:
                get_client("deepseek")
            assert "Missing API key" in str(exc_info.value)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)


class TestGetAsyncClient:
    """Tests for get_async_client() function."""

    def test_get_async_client_returns_async_openai(self):
        """get_async_client returns AsyncOpenAI instance."""
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_MODEL": "deepseek-chat"},
        ):
            client, model = get_async_client("deepseek")
            # AsyncOpenAI is returned
            assert hasattr(client, "chat")
            assert hasattr(client.chat.completions, "create")
            assert model == "deepseek-chat"


# === AC-3: 5xx/network errors trigger fallback, 4xx do not ===


class TestIsRetryableError:
    """Tests for _is_retryable_error() function."""

    def test_5xx_is_retryable(self):
        """5xx server errors should trigger fallback."""
        # Create mock response and use real APIStatusError
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.request = MagicMock()
        # APIStatusError(message, response, body) - need proper args
        try:
            error = APIStatusError("500 error", response=mock_response, body=None)
        except TypeError:
            # Fallback to simpler mock if constructor doesn't match
            error = MagicMock(spec=APIStatusError)
            error.status_code = 500
        assert _is_retryable_error(error) is True

    def test_4xx_is_not_retryable(self):
        """4xx client errors should NOT trigger fallback."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.request = MagicMock()
        try:
            error = APIStatusError("401 error", response=mock_response, body=None)
        except TypeError:
            error = MagicMock(spec=APIStatusError)
            error.status_code = 401
        assert _is_retryable_error(error) is False

    def test_connection_error_is_retryable(self):
        """Network connection errors should trigger fallback."""
        mock_request = Request("GET", "https://api.example.com")
        try:
            error = APIConnectionError(request=mock_request)
        except TypeError:
            error = MagicMock(spec=APIConnectionError)
        assert _is_retryable_error(error) is True

    def test_timeout_is_retryable(self):
        """Timeout errors should trigger fallback."""
        assert _is_retryable_error(TimeoutError()) is True


# === AC-2 & AC-4: Fallback chain with async ===


class TestCallLLMWithFallback:
    """Tests for call_llm_with_fallback() async function."""

    @pytest.mark.asyncio
    async def test_fallback_on_5xx_deepseek_to_doubao(self):
        """AC-4: DeepSeek 5xx → fallback to Doubao succeeds."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Doubao response"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_response.model_dump.return_value = {"id": "test"}

        # Create mock that fails for deepseek, succeeds for doubao
        mock_deepseek_client = MagicMock()
        # APIConnectionError requires request kwarg
        mock_request = Request("GET", "https://api.example.com")
        mock_deepseek_client.chat.completions.create = AsyncMock(
            side_effect=APIConnectionError(request=mock_request)
        )

        mock_doubao_client = MagicMock()
        mock_doubao_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "deepseek-key",
                "ARK_API_KEY": "doubao-key",
                "ARK_MODEL_ENDPOINT_ID": "ep-test",
            },
        ):
            with patch(
                "app.llm_multi_provider.get_async_client"
            ) as mock_get_client:
                def side_effect(provider):
                    if provider == "deepseek":
                        return mock_deepseek_client, "deepseek-chat"
                    elif provider == "doubao":
                        return mock_doubao_client, "ep-test"
                    raise ProviderConfigError(f"Unexpected: {provider}")

                mock_get_client.side_effect = side_effect

                result = await call_llm_with_fallback(
                    [{"role": "user", "content": "test"}],
                    fallback_order=["deepseek", "doubao"],
                )

                assert result.content == "Doubao response"
                assert result.usage.provider == "doubao"
                assert result.usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_no_fallback_on_4xx(self):
        """AC-3: 4xx errors (auth/quota) should NOT trigger fallback."""
        mock_client = MagicMock()
        # Create a generic Exception that won't be retried
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("Auth error - non-retryable")
        )

        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "test-key"},
        ):
            with patch(
                "app.llm_multi_provider.get_async_client"
            ) as mock_get_client:
                mock_get_client.return_value = (mock_client, "deepseek-chat")

                # Should raise Exception (no fallback)
                with pytest.raises(Exception) as exc_info:
                    await call_llm_with_fallback(
                        [{"role": "user", "content": "test"}],
                        fallback_order=["deepseek", "doubao"],
                    )

                # Should be the original error, not fallback
                assert "Auth error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_all_providers_failed_raises_error(self):
        """When all providers fail, raise AllProvidersFailedError."""
        mock_client = MagicMock()
        # APIConnectionError requires request kwarg
        mock_request = Request("GET", "https://api.example.com")
        mock_client.chat.completions.create = AsyncMock(
            side_effect=APIConnectionError(request=mock_request)
        )

        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "key1",
                "ARK_API_KEY": "key2",
            },
        ):
            with patch(
                "app.llm_multi_provider.get_async_client"
            ) as mock_get_client:
                mock_get_client.return_value = (mock_client, "test-model")

                with pytest.raises(AllProvidersFailedError) as exc_info:
                    await call_llm_with_fallback(
                        [{"role": "user", "content": "test"}],
                        fallback_order=["deepseek", "doubao"],
                    )

                assert len(exc_info.value.errors) == 2

    @pytest.mark.asyncio
    async def test_provider_override_changes_order(self):
        """provider_override parameter should change fallback order."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Qwen response"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_response.model_dump.return_value = {}

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.dict(
            os.environ,
            {"DASHSCOPE_API_KEY": "qwen-key", "QWEN_MODEL": "qwen-plus"},
        ):
            with patch(
                "app.llm_multi_provider.get_async_client"
            ) as mock_get_client:
                mock_get_client.return_value = (mock_client, "qwen-plus")

                result = await call_llm_with_fallback(
                    [{"role": "user", "content": "test"}],
                    provider_override="qwen",
                    fallback_order=["deepseek", "doubao", "qwen"],
                )

                # Should have called qwen first (via override)
                assert result.usage.provider == "qwen"


# === AC-5: Token telemetry ===


class TestTokenTelemetry:
    """Tests for token usage telemetry."""

    @pytest.mark.asyncio
    async def test_usage_includes_all_token_fields(self):
        """AC-5: LLMResponse.usage must include prompt/completion/total tokens."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.model_dump.return_value = {"id": "test-id"}

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "test-key"},
        ):
            with patch(
                "app.llm_multi_provider.get_async_client"
            ) as mock_get_client:
                mock_get_client.return_value = (mock_client, "deepseek-chat")

                result = await call_llm_single(
                    [{"role": "user", "content": "test"}],
                    provider="deepseek",
                )

                assert result.usage.prompt_tokens == 100
                assert result.usage.completion_tokens == 50
                assert result.usage.total_tokens == 150
                assert result.usage.provider == "deepseek"
                assert result.usage.model == "deepseek-chat"

    def test_llm_usage_dataclass(self):
        """LLMUsage dataclass should store all fields correctly."""
        usage = LLMUsage(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            provider="deepseek",
            model="deepseek-chat",
        )

        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 5
        assert usage.total_tokens == 15
        assert usage.provider == "deepseek"
        assert usage.model == "deepseek-chat"


class TestCallLLMSingle:
    """Tests for call_llm_single() convenience function."""

    @pytest.mark.asyncio
    async def test_single_provider_success(self):
        """call_llm_single should work for a single provider without fallback."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Single provider response"
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 10
        mock_response.usage.total_tokens = 30
        mock_response.model_dump.return_value = {}

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "test-key"},
        ):
            with patch(
                "app.llm_multi_provider.get_async_client"
            ) as mock_get_client:
                mock_get_client.return_value = (mock_client, "deepseek-chat")

                result = await call_llm_single(
                    [{"role": "user", "content": "Hello"}],
                    provider="deepseek",
                )

                assert result.content == "Single provider response"
                assert result.usage.provider == "deepseek"


class TestDefaultFallbackOrder:
    """Tests for default fallback order configuration."""

    def test_default_order_includes_all_providers(self):
        """Default fallback order should include all 5 providers."""
        assert DEFAULT_FALLBACK_ORDER == ["deepseek", "glm", "doubao", "qwen", "minimax"]

    def test_default_order_deepseek_first(self):
        """DeepSeek should be the primary provider."""
        assert DEFAULT_FALLBACK_ORDER[0] == "deepseek"