"""Tests for src/ai/summarizer.py — news summariser."""

from __future__ import annotations

import pytest

from src.ai.client import LLMResponse, MockLLMClient
from src.ai.summarizer import ArticleInput, NewsSummarizer, SummaryResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="mock",
        provider="mock",
        input_tokens=50,
        output_tokens=100,
        latency_ms=1.0,
    )


COMPLETE_RESPONSE = """\
**O que aconteceu**
O STF decidiu, por unanimidade, que a lei de transparência das emendas \
parlamentares é constitucional.

**Por que importa**
A decisão fortalece o controle social sobre o orçamento público e exige \
maior publicidade dos gastos.

**Contexto institucional**
O Supremo Tribunal Federal é o guardião da Constituição e age como árbitro \
dos conflitos entre os poderes.

**Tags sugeridas**
#STF, #transparência, #emendas, #orçamento
"""


INCOMPLETE_RESPONSE = """\
**O que aconteceu**
O STF se reuniu para debater a questão.
"""


# ---------------------------------------------------------------------------
# SummaryResult.parse()
# ---------------------------------------------------------------------------


class TestSummaryResultParse:
    """Unit tests for SummaryResult.parse() section extraction."""

    def test_parse_extracts_what_happened(self):
        result = SummaryResult.parse(_make_response(COMPLETE_RESPONSE))
        assert "STF decidiu" in result.what_happened

    def test_parse_extracts_why_it_matters(self):
        result = SummaryResult.parse(_make_response(COMPLETE_RESPONSE))
        assert "controle social" in result.why_it_matters

    def test_parse_extracts_institutional_context(self):
        result = SummaryResult.parse(_make_response(COMPLETE_RESPONSE))
        assert "Supremo Tribunal Federal" in result.institutional_context

    def test_parse_extracts_tags(self):
        result = SummaryResult.parse(_make_response(COMPLETE_RESPONSE))
        assert "STF" in result.suggested_tags
        assert "transparência" in result.suggested_tags
        assert "emendas" in result.suggested_tags

    def test_parse_stores_raw_text(self):
        result = SummaryResult.parse(_make_response(COMPLETE_RESPONSE))
        assert result.raw_text == COMPLETE_RESPONSE

    def test_parse_stores_response_object(self):
        resp = _make_response(COMPLETE_RESPONSE)
        result = SummaryResult.parse(resp)
        assert result.response is resp

    def test_is_complete_when_all_sections_present(self):
        result = SummaryResult.parse(_make_response(COMPLETE_RESPONSE))
        assert result.is_complete is True

    def test_is_complete_false_when_sections_missing(self):
        result = SummaryResult.parse(_make_response(INCOMPLETE_RESPONSE))
        assert result.is_complete is False

    def test_parse_empty_response_gives_empty_fields(self):
        result = SummaryResult.parse(_make_response(""))
        assert result.what_happened == ""
        assert result.why_it_matters == ""
        assert result.institutional_context == ""
        assert result.suggested_tags == []

    def test_tags_strip_hash_prefix(self):
        result = SummaryResult.parse(_make_response(COMPLETE_RESPONSE))
        for tag in result.suggested_tags:
            assert not tag.startswith("#")


# ---------------------------------------------------------------------------
# NewsSummarizer (with MockLLMClient)
# ---------------------------------------------------------------------------


class TestNewsSummarizer:
    """Integration tests for NewsSummarizer using MockLLMClient."""

    def _make_article(
        self,
        title: str = "STF julga emendas parlamentares",
        text: str = "word " * 200,
        url: str = "https://example.com/article",
    ) -> ArticleInput:
        return ArticleInput(
            url=url,
            title=title,
            text=text,
            source_name="Agência Brasil",
            tags=["política"],
            kb_context="",
        )

    def test_summarize_returns_summary_result(self):
        mock_client = MockLLMClient(COMPLETE_RESPONSE)
        summarizer = NewsSummarizer(client=mock_client)
        result = summarizer.summarize(self._make_article())
        assert isinstance(result, SummaryResult)

    def test_summarize_calls_client_once(self):
        mock_client = MockLLMClient(COMPLETE_RESPONSE)
        summarizer = NewsSummarizer(client=mock_client)
        summarizer.summarize(self._make_article())
        assert len(mock_client.calls) == 1

    def test_summarize_passes_title_to_prompt(self):
        mock_client = MockLLMClient(COMPLETE_RESPONSE)
        summarizer = NewsSummarizer(client=mock_client)
        summarizer.summarize(self._make_article(title="Lula veta projeto"))
        user_prompt = mock_client.calls[0]["user"]
        assert "Lula veta projeto" in user_prompt

    def test_summarize_truncates_long_text(self):
        """Text over 3000 words should be truncated before sending to LLM."""
        mock_client = MockLLMClient(COMPLETE_RESPONSE)
        summarizer = NewsSummarizer(client=mock_client)
        long_text = "palavra " * 5000  # way over 3000 words
        summarizer.summarize(self._make_article(text=long_text))
        user_prompt = mock_client.calls[0]["user"]
        # The sent prompt should not contain all 5000 words
        word_count = len(user_prompt.split())
        assert word_count < 4000  # should be truncated

    def test_summarize_includes_kb_context(self):
        mock_client = MockLLMClient(COMPLETE_RESPONSE)
        summarizer = NewsSummarizer(client=mock_client)
        article = self._make_article()
        article.kb_context = "O STF é composto por 11 ministros."
        summarizer.summarize(article)
        user_prompt = mock_client.calls[0]["user"]
        assert "STF é composto por 11 ministros" in user_prompt

    @pytest.mark.asyncio
    async def test_asummarize_returns_summary_result(self):
        mock_client = MockLLMClient(COMPLETE_RESPONSE)
        summarizer = NewsSummarizer(client=mock_client)
        result = await summarizer.asummarize(self._make_article())
        assert isinstance(result, SummaryResult)
