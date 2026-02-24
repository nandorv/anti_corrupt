"""
LLM abstraction layer.

Supports:
  - Anthropic Claude (primary)
  - OpenAI GPT-4o (fallback / cost comparison)

Usage::

    from src.ai.client import get_client, LLMResponse

    client = get_client()                            # uses settings
    resp   = client.complete(system=..., user=...)  # sync
    resp   = await client.acomplete(...)             # async
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Response container
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """Unified response from any LLM backend."""

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    raw: object = field(default=None, repr=False)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        """Rough cost estimate in USD (prices as of 2024)."""
        PRICES = {
            # (input $/1M, output $/1M)
            "claude-sonnet-4-20250514": (3.0, 15.0),
            "claude-3-5-sonnet-20241022": (3.0, 15.0),
            "claude-3-haiku-20240307": (0.25, 1.25),
            "gpt-4o": (5.0, 15.0),
            "gpt-4o-mini": (0.15, 0.60),
        }
        inp_price, out_price = PRICES.get(self.model, (3.0, 15.0))
        return (self.input_tokens * inp_price + self.output_tokens * out_price) / 1_000_000


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseLLMClient(ABC):
    """Common interface for all LLM backends."""

    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Synchronous completion."""
        ...

    @abstractmethod
    async def acomplete(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Asynchronous completion."""
        ...


# ---------------------------------------------------------------------------
# Anthropic backend
# ---------------------------------------------------------------------------


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude backend."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str, default_model: str | None = None) -> None:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError("Install anthropic: uv add anthropic") from exc

        self._client = anthropic.Anthropic(api_key=api_key)
        self._async_client = anthropic.AsyncAnthropic(api_key=api_key)
        self.default_model = default_model or self.DEFAULT_MODEL

    def complete(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        model = model or self.default_model
        t0 = time.perf_counter()
        msg = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        latency = (time.perf_counter() - t0) * 1000
        content = msg.content[0].text if msg.content else ""
        return LLMResponse(
            content=content,
            model=model,
            provider="anthropic",
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            latency_ms=latency,
            raw=msg,
        )

    async def acomplete(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        model = model or self.default_model
        t0 = time.perf_counter()
        msg = await self._async_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        latency = (time.perf_counter() - t0) * 1000
        content = msg.content[0].text if msg.content else ""
        return LLMResponse(
            content=content,
            model=model,
            provider="anthropic",
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            latency_ms=latency,
            raw=msg,
        )


# ---------------------------------------------------------------------------
# OpenAI backend
# ---------------------------------------------------------------------------


class OpenAIClient(BaseLLMClient):
    """OpenAI GPT backend."""

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, api_key: str, default_model: str | None = None) -> None:
        try:
            from openai import AsyncOpenAI, OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError("Install openai: uv add openai") from exc

        self._client = OpenAI(api_key=api_key)
        self._async_client = AsyncOpenAI(api_key=api_key)
        self.default_model = default_model or self.DEFAULT_MODEL

    def complete(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        model = model or self.default_model
        t0 = time.perf_counter()
        resp = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        latency = (time.perf_counter() - t0) * 1000
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        return LLMResponse(
            content=content,
            model=model,
            provider="openai",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency,
            raw=resp,
        )

    async def acomplete(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        model = model or self.default_model
        t0 = time.perf_counter()
        resp = await self._async_client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        latency = (time.perf_counter() - t0) * 1000
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        return LLMResponse(
            content=content,
            model=model,
            provider="openai",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency,
            raw=resp,
        )


# ---------------------------------------------------------------------------
# Mock client (for tests / dry-run mode)
# ---------------------------------------------------------------------------


class MockLLMClient(BaseLLMClient):
    """Returns canned responses without calling any API.  Used in tests."""

    def __init__(self, fixed_response: str = "[MOCK RESPONSE]") -> None:
        self.fixed_response = fixed_response
        self.calls: list[dict] = []

    def complete(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        self.calls.append({"system": system, "user": user})
        return LLMResponse(
            content=self.fixed_response,
            model=model or "mock",
            provider="mock",
            input_tokens=len(system.split()) + len(user.split()),
            output_tokens=len(self.fixed_response.split()),
            latency_ms=1.0,
        )

    async def acomplete(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        return self.complete(system, user, model, max_tokens, temperature)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_client(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    mock: bool = False,
) -> BaseLLMClient:
    """
    Build and return the appropriate LLM client.

    Resolution order:
      1. *mock=True* → MockLLMClient
      2. *provider* kwarg
      3. ``ANTHROPIC_API_KEY`` env var → AnthropicClient
      4. ``OPENAI_API_KEY`` env var    → OpenAIClient
      5. No key found                  → MockLLMClient with a warning
    """
    if mock:
        return MockLLMClient()

    # Lazy import to avoid circular dependency with config.settings at module load
    from config.settings import settings  # noqa: PLC0415

    resolved_provider = provider or _detect_provider(settings)

    if resolved_provider == "anthropic":
        key = api_key or settings.anthropic_api_key
        if not key:
            logger.warning("ANTHROPIC_API_KEY not set — using mock client")
            return MockLLMClient()
        return AnthropicClient(api_key=key, default_model=model)

    if resolved_provider == "openai":
        key = api_key or settings.openai_api_key
        if not key:
            logger.warning("OPENAI_API_KEY not set — using mock client")
            return MockLLMClient()
        return OpenAIClient(api_key=key, default_model=model)

    logger.warning("No LLM API key configured — using mock client")
    return MockLLMClient()


def _detect_provider(settings: object) -> str:
    if getattr(settings, "anthropic_api_key", None):
        return "anthropic"
    if getattr(settings, "openai_api_key", None):
        return "openai"
    return "mock"
