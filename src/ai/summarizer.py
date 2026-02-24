"""
AI-powered news summariser.

Turns a raw article (title + body text) into a structured PT-BR summary
ready for editorial review.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.ai.client import BaseLLMClient, LLMResponse, get_client
from src.ai.prompts import get_prompt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input / output containers
# ---------------------------------------------------------------------------


@dataclass
class ArticleInput:
    """Article data passed to the summariser."""

    url: str
    title: str
    text: str  # full body text
    source_name: str = ""
    tags: list[str] = field(default_factory=list)
    kb_context: str = ""  # optional KB enrichment injected by caller


@dataclass
class SummaryResult:
    """Parsed output from the summariser."""

    raw_text: str           # full LLM response text
    what_happened: str = ""
    why_it_matters: str = ""
    institutional_context: str = ""
    suggested_tags: list[str] = field(default_factory=list)
    response: Optional[LLMResponse] = None

    @classmethod
    def parse(cls, response: LLMResponse) -> "SummaryResult":
        """Extract structured sections from the LLM markdown response."""
        text = response.content
        obj = cls(raw_text=text, response=response)

        sections = {
            "**O que aconteceu**": "what_happened",
            "**Por que importa**": "why_it_matters",
            "**Contexto institucional**": "institutional_context",
            "**Tags sugeridas**": "suggested_tags",
        }

        lines = text.splitlines()
        current_key: Optional[str] = None
        buffer: list[str] = []

        for line in lines:
            stripped = line.strip()
            matched = False
            for header, attr in sections.items():
                if stripped.startswith(header):
                    # Save previous section
                    if current_key:
                        _set_section(obj, current_key, buffer)
                    current_key = attr
                    buffer = []
                    matched = True
                    break
            if not matched and current_key:
                buffer.append(line)

        # Save final section
        if current_key:
            _set_section(obj, current_key, buffer)

        return obj

    @property
    def is_complete(self) -> bool:
        return bool(
            self.what_happened
            and self.why_it_matters
            and self.institutional_context
        )


def _set_section(obj: SummaryResult, key: str, buffer: list[str]) -> None:
    content = "\n".join(buffer).strip()
    if key == "suggested_tags":
        # Parse comma-separated tags
        tags = [t.strip().lstrip("#") for t in content.split(",") if t.strip()]
        obj.suggested_tags = tags
    else:
        setattr(obj, key, content)


# ---------------------------------------------------------------------------
# Summariser class
# ---------------------------------------------------------------------------


class NewsSummarizer:
    """Wraps the summarize_news prompt + LLM client."""

    def __init__(self, client: Optional[BaseLLMClient] = None) -> None:
        self.client = client or get_client()
        self._prompt = get_prompt("summarize_news")

    def summarize(self, article: ArticleInput) -> SummaryResult:
        """Summarize a single article synchronously."""
        # Truncate to ~3 000 words to stay within context
        truncated_text = _truncate(article.text, max_words=3000)
        article_block = f"**{article.title}**\n\n{truncated_text}"

        system, user = self._prompt.render(
            article_text=article_block,
            kb_context=article.kb_context or "Nenhum contexto adicional disponível.",
        )

        logger.info("Summarizing: %s", article.title[:80])
        response = self.client.complete(
            system=system,
            user=user,
            model=self._prompt.model,
            max_tokens=self._prompt.max_tokens,
            temperature=self._prompt.temperature,
        )

        result = SummaryResult.parse(response)
        if not result.is_complete:
            logger.warning("Incomplete summary for: %s", article.title[:80])
        return result

    async def asummarize(self, article: ArticleInput) -> SummaryResult:
        """Summarize asynchronously."""
        truncated_text = _truncate(article.text, max_words=3000)
        article_block = f"**{article.title}**\n\n{truncated_text}"

        system, user = self._prompt.render(
            article_text=article_block,
            kb_context=article.kb_context or "Nenhum contexto adicional disponível.",
        )

        response = await self.client.acomplete(
            system=system,
            user=user,
            model=self._prompt.model,
            max_tokens=self._prompt.max_tokens,
            temperature=self._prompt.temperature,
        )
        return SummaryResult.parse(response)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "\n\n[... texto truncado para análise ...]"
