"""Tests for src/ai/client.py — LLM abstraction layer."""

from __future__ import annotations

import pytest

from src.ai.client import LLMResponse, MockLLMClient


# ---------------------------------------------------------------------------
# LLMResponse
# ---------------------------------------------------------------------------


class TestLLMResponse:
    """Unit tests for the LLMResponse dataclass."""

    def _make(
        self,
        content: str = "Resposta gerada.",
        model: str = "mock",
        provider: str = "mock",
        input_tokens: int = 100,
        output_tokens: int = 50,
    ) -> LLMResponse:
        return LLMResponse(
            content=content,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=10.0,
        )

    def test_total_tokens(self):
        resp = self._make(input_tokens=100, output_tokens=50)
        assert resp.total_tokens == 150

    def test_estimated_cost_known_model(self):
        resp = self._make(
            model="claude-sonnet-4-20250514",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        # Input price is $3/1M
        assert abs(resp.estimated_cost_usd - 3.0) < 0.001

    def test_estimated_cost_unknown_model_uses_default(self):
        resp = self._make(
            model="unknown-model-xyz",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        # Default is $3/1M for input
        assert abs(resp.estimated_cost_usd - 3.0) < 0.001

    def test_estimated_cost_output_tokens(self):
        resp = self._make(
            model="claude-sonnet-4-20250514",
            input_tokens=0,
            output_tokens=1_000_000,
        )
        # Output price is $15/1M
        assert abs(resp.estimated_cost_usd - 15.0) < 0.001

    def test_zero_cost_with_zero_tokens(self):
        resp = self._make(input_tokens=0, output_tokens=0)
        assert resp.estimated_cost_usd == 0.0

    def test_content_stored(self):
        resp = self._make(content="Test content")
        assert resp.content == "Test content"

    def test_provider_stored(self):
        resp = self._make(provider="anthropic")
        assert resp.provider == "anthropic"


# ---------------------------------------------------------------------------
# MockLLMClient
# ---------------------------------------------------------------------------


class TestMockLLMClient:
    """Unit tests for MockLLMClient."""

    def test_complete_returns_llm_response(self):
        client = MockLLMClient("hello world")
        resp = client.complete(system="system", user="user prompt")
        assert isinstance(resp, LLMResponse)

    def test_complete_returns_fixed_response(self):
        client = MockLLMClient("fixed output")
        resp = client.complete(system="sys", user="usr")
        assert resp.content == "fixed output"

    def test_provider_is_mock(self):
        client = MockLLMClient()
        resp = client.complete(system="s", user="u")
        assert resp.provider == "mock"

    def test_calls_are_recorded(self):
        client = MockLLMClient()
        client.complete(system="system-1", user="user-1")
        client.complete(system="system-2", user="user-2")
        assert len(client.calls) == 2
        assert client.calls[0]["system"] == "system-1"
        assert client.calls[1]["user"] == "user-2"

    def test_default_fixed_response(self):
        client = MockLLMClient()
        resp = client.complete(system="s", user="u")
        assert "[MOCK RESPONSE]" in resp.content

    def test_input_tokens_estimated_from_word_count(self):
        client = MockLLMClient()
        resp = client.complete(system="one two three", user="four five")
        # system=3 words + user=2 words = 5
        assert resp.input_tokens == 5

    def test_custom_model_stored(self):
        client = MockLLMClient()
        resp = client.complete(system="s", user="u", model="custom-model")
        assert resp.model == "custom-model"

    def test_default_model_is_mock(self):
        client = MockLLMClient()
        resp = client.complete(system="s", user="u")
        assert resp.model == "mock"

    @pytest.mark.asyncio
    async def test_acomplete_returns_llm_response(self):
        client = MockLLMClient("async response")
        resp = await client.acomplete(system="s", user="u")
        assert isinstance(resp, LLMResponse)
        assert resp.content == "async response"

    @pytest.mark.asyncio
    async def test_acomplete_records_call(self):
        client = MockLLMClient()
        await client.acomplete(system="async-sys", user="async-usr")
        assert len(client.calls) == 1
        assert client.calls[0]["system"] == "async-sys"
