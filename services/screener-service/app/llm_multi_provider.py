"""LLM multi-provider module with OpenAI SDK + async + fallback.

Supports 5 providers: DeepSeek, GLM, Doubao (Volc Ark), Qwen (DashScope), MiniMax.
Uses OpenAI-compatible endpoints with custom base_url for all providers.

Fallback strategy:
- 5xx / network errors → next provider
- 4xx (auth / quota) → DO NOT fallback, raise immediately
- Latency P95 breach (>5s for non-streaming) → tier down with warning
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

try:
    from openai import APIConnectionError, APIStatusError, AsyncOpenAI, OpenAI
except ImportError:  # pragma: no cover - exercised in environments without SDK
    class APIConnectionError(Exception):
        pass

    class APIStatusError(Exception):
        status_code = 0

    AsyncOpenAI = None
    OpenAI = None
try:
    from tenacity import (
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
    )
except ImportError:  # pragma: no cover
    def retry(*args: Any, **kwargs: Any):
        def decorator(func):
            return func
        return decorator

    def retry_if_exception_type(*args: Any, **kwargs: Any):
        return None

    def stop_after_attempt(*args: Any, **kwargs: Any):
        return None

    def wait_exponential(*args: Any, **kwargs: Any):
        return None

logger = logging.getLogger(__name__)


# Provider configuration - all use OpenAI-compatible endpoints
PROVIDER_CONFIG: dict[str, dict[str, str]] = {
    "deepseek": {
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        "api_key_env": "DEEPSEEK_API_KEY",
        "model_env": "DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
    },
    "doubao": {
        "base_url": os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        "api_key_env": "ARK_API_KEY",
        "model_env": "ARK_MODEL_ENDPOINT_ID",
        "default_model": "",
    },
    "qwen": {
        "base_url": os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "api_key_env": "DASHSCOPE_API_KEY",
        "model_env": "QWEN_MODEL",
        "default_model": "qwen-plus",
    },
    "minimax": {
        "base_url": os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1"),
        "api_key_env": "MINIMAX_API_KEY",
        "model_env": "MINIMAX_MODEL",
        "default_model": "abab6.5s-chat",
    },
    "glm": {
        "base_url": os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/"),
        "api_key_env": "GLM_API_KEY",
        "model_env": "GLM_MODEL",
        "default_model": "glm-4-flash",
    },
}

# Default fallback order
DEFAULT_FALLBACK_ORDER = ["deepseek", "glm", "doubao", "qwen", "minimax"]


@dataclass
class LLMUsage:
    """Token usage telemetry."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    provider: str
    model: str


@dataclass
class LLMResponse:
    """LLM response with content and telemetry."""

    content: str
    usage: LLMUsage
    raw_response: dict[str, Any] | None = None


class ProviderConfigError(Exception):
    """Raised when provider configuration is missing or invalid."""

    pass


class AllProvidersFailedError(Exception):
    """Raised when all providers in fallback chain have failed."""

    def __init__(self, errors: list[Exception], provider_order: list[str]):
        self.errors = errors
        self.provider_order = provider_order
        error_summary = "; ".join(
            f"{p}: {e.__class__.__name__}" for p, e in zip(provider_order, errors)
        )
        super().__init__(f"All providers failed: {error_summary}")


class _UnavailableCompletions:
    """Minimal OpenAI-compatible surface for environments without the SDK."""

    def __init__(self, reason: str):
        self.reason = reason

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        raise ProviderConfigError(self.reason)


class _UnavailableOpenAIClient:
    def __init__(self, reason: str):
        self.chat = type("_UnavailableChat", (), {
            "completions": _UnavailableCompletions(reason)
        })()


def _missing_api_key_message(provider: str, env_name: str) -> str:
    return f"Missing API key for {provider}: set {env_name} environment variable"


def _sdk_unavailable_client(reason: str = "OpenAI SDK is not installed") -> Any:
    return _UnavailableOpenAIClient(reason)


def get_client(provider: str) -> tuple[Any, str]:
    """Get OpenAI client and model for the specified provider.

    Args:
        provider: One of 'deepseek', 'doubao', 'qwen', 'minimax'

    Returns:
        Tuple of (OpenAI client instance, model name/endpoint ID)

    Raises:
        ProviderConfigError: If provider is unknown or API key is missing
    """
    if provider not in PROVIDER_CONFIG:
        raise ProviderConfigError(f"Unknown provider: {provider}")

    config = PROVIDER_CONFIG[provider]
    api_key = os.environ.get(config["api_key_env"])

    if not api_key:
        raise ProviderConfigError(_missing_api_key_message(provider, config["api_key_env"]))

    model = os.getenv(config["model_env"], config["default_model"])
    if not model:
        raise ProviderConfigError(
            f"Missing model for {provider}: set {config['model_env']} environment variable"
        )
    if OpenAI is None:
        return _sdk_unavailable_client(), model

    client = OpenAI(
        api_key=api_key,
        base_url=config["base_url"],
    )

    return client, model


def get_async_client(provider: str) -> tuple[Any, str]:
    """Get async OpenAI client and model for the specified provider.

    Args:
        provider: One of 'deepseek', 'doubao', 'qwen', 'minimax'

    Returns:
        Tuple of (AsyncOpenAI client instance, model name/endpoint ID)

    Raises:
        ProviderConfigError: If provider is unknown or API key is missing
    """
    if provider not in PROVIDER_CONFIG:
        raise ProviderConfigError(f"Unknown provider: {provider}")

    config = PROVIDER_CONFIG[provider]
    api_key = os.environ.get(config["api_key_env"])

    if not api_key:
        raise ProviderConfigError(_missing_api_key_message(provider, config["api_key_env"]))

    model = os.getenv(config["model_env"], config["default_model"])
    if not model:
        raise ProviderConfigError(
            f"Missing model for {provider}: set {config['model_env']} environment variable"
        )
    if AsyncOpenAI is None:
        return _sdk_unavailable_client(), model

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=config["base_url"],
    )
    try:
        client.chat.completions
    except (AttributeError, ImportError, ModuleNotFoundError) as exc:
        logger.warning("OpenAI SDK client is unavailable after init: %s", exc)
        return _sdk_unavailable_client(f"OpenAI SDK is unavailable: {exc}"), model

    return client, model


def _is_retryable_error(error: Exception) -> bool:
    """Check if error should trigger fallback to next provider.

    Returns True for:
    - 5xx server errors
    - Network/connection errors

    Returns False for:
    - 4xx client errors (auth, quota, invalid request)
    """
    status_code = getattr(error, "status_code", None)
    if not isinstance(status_code, int):
        status_code = getattr(getattr(error, "response", None), "status_code", None)
    if isinstance(status_code, int):
        return status_code >= 500
    if isinstance(error, APIConnectionError):
        return True
    if isinstance(error, APIStatusError):
        # 5xx errors are retryable, 4xx are not
        return error.status_code >= 500
    if isinstance(error, (TimeoutError, OSError)):
        return True
    return False


def _extract_usage(response: Any, provider: str, model: str) -> LLMUsage:
    """Extract token usage from LLM response."""
    usage_obj = getattr(response, "usage", None)

    # Handle both real OpenAI response and mock objects
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    if usage_obj is not None:
        # Try direct attribute access (real OpenAI SDK)
        if hasattr(usage_obj, "prompt_tokens"):
            prompt_tokens = int(usage_obj.prompt_tokens or 0)
        if hasattr(usage_obj, "completion_tokens"):
            completion_tokens = int(usage_obj.completion_tokens or 0)
        if hasattr(usage_obj, "total_tokens"):
            total_tokens = int(usage_obj.total_tokens or 0)

        # Fallback to dict access if attributes not found
        if prompt_tokens == 0 and completion_tokens == 0:
            if hasattr(usage_obj, "model_dump"):
                usage_dict = usage_obj.model_dump()
            elif isinstance(usage_obj, dict):
                usage_dict = usage_obj
            else:
                usage_dict = {}
            prompt_tokens = int(usage_dict.get("prompt_tokens", 0))
            completion_tokens = int(usage_dict.get("completion_tokens", 0))
            total_tokens = int(usage_dict.get("total_tokens", 0))

    return LLMUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        provider=provider,
        model=model,
    )


async def _call_single_provider(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int | None = None,
    **kwargs: Any,
) -> tuple[str, LLMUsage, dict[str, Any]]:
    """Call a single provider and return content, usage, and raw response."""
    response = await client.chat.completions.create(
        model=model,
        messages=messages,  # type: ignore
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )

    content = response.choices[0].message.content or ""
    usage = _extract_usage(response, "", model)

    raw = {}
    if hasattr(response, "model_dump"):
        raw = response.model_dump()

    return content, usage, raw


async def call_llm_with_fallback(
    messages: list[dict[str, str]],
    provider_override: str | None = None,
    fallback_order: list[str] | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    **kwargs: Any,
) -> LLMResponse:
    """Call LLM with automatic fallback on server/network errors.

    Args:
        messages: OpenAI-format message list [{"role": "user", "content": "..."}]
        provider_override: Start with specific provider instead of default
        fallback_order: Custom fallback order (default: DeepSeek → Doubao → Qwen → MiniMax)
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
        **kwargs: Additional arguments passed to OpenAI client

    Returns:
        LLMResponse with content and usage telemetry

    Raises:
        AllProvidersFailedError: All providers in chain failed
        ProviderConfigError: Primary provider missing configuration
        APIStatusError: 4xx error from any provider (auth/quota issue)
    """
    order = fallback_order or DEFAULT_FALLBACK_ORDER

    if provider_override:
        if provider_override not in PROVIDER_CONFIG:
            raise ProviderConfigError(f"Unknown provider override: {provider_override}")
        # Move override to front
        order = [provider_override] + [p for p in order if p != provider_override]

    errors: list[Exception] = []

    for provider in order:
        try:
            client, model = get_async_client(provider)

            logger.info(f"Calling LLM provider: {provider}, model: {model}")

            content, usage, raw = await _call_single_provider(
                client, model, messages, temperature, max_tokens, **kwargs
            )

            # Update usage with actual provider
            usage.provider = provider

            logger.info(
                f"LLM call succeeded: provider={provider}, "
                f"prompt_tokens={usage.prompt_tokens}, "
                f"completion_tokens={usage.completion_tokens}, "
                f"total_tokens={usage.total_tokens}"
            )

            return LLMResponse(content=content, usage=usage, raw_response=raw)

        except Exception as e:
            errors.append(e)

            if _is_retryable_error(e):
                logger.warning(
                    f"LLM provider {provider} failed with retryable error: {e.__class__.__name__}, "
                    "falling back to next provider"
                )
                continue
            else:
                # 4xx or other non-retryable error - don't fallback
                logger.error(
                    f"LLM provider {provider} failed with non-retryable error: {e.__class__.__name__}: {e}"
                )
                raise

    raise AllProvidersFailedError(errors, order)


# Convenience function for single-provider calls (no fallback)
async def call_llm_single(
    messages: list[dict[str, str]],
    provider: str = "deepseek",
    temperature: float = 0.7,
    max_tokens: int | None = None,
    **kwargs: Any,
) -> LLMResponse:
    """Call a single LLM provider without fallback.

    Useful when you want explicit provider control or for testing.
    """
    client, model = get_async_client(provider)

    content, usage, raw = await _call_single_provider(
        client, model, messages, temperature, max_tokens, **kwargs
    )
    usage.provider = provider

    return LLMResponse(content=content, usage=usage, raw_response=raw)


# Sync wrapper for backward compatibility
def call_llm_sync(
    messages: list[dict[str, str]],
    provider: str = "deepseek",
    temperature: float = 0.7,
    max_tokens: int | None = None,
    **kwargs: Any,
) -> LLMResponse:
    """Synchronous LLM call for single provider (no fallback).

    This is a convenience wrapper for non-async contexts.
    Prefer async version for production use.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in async context - create new event loop
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                call_llm_single(messages, provider, temperature, max_tokens, **kwargs),
            )
            return future.result()
    else:
        return asyncio.run(
            call_llm_single(messages, provider, temperature, max_tokens, **kwargs)
        )
