"""
Content formatter — converts ContentDraft body text into platform-specific formats.

Supported output formats:
  - Instagram carousel (slide-by-slide text, 2 200 char limit per caption)
  - X/Twitter thread (numbered tweets, 280 chars each)
  - Threads post (plain text, 500 chars)
  - Newsletter section (Markdown-friendly HTML fragment)
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field

from src.content.models import ContentDraft, ContentType, Platform

# ---------------------------------------------------------------------------
# Output containers
# ---------------------------------------------------------------------------

INSTAGRAM_CAPTION_LIMIT = 2200
X_TWEET_LIMIT = 280
THREADS_POST_LIMIT = 500


@dataclass
class InstagramCarousel:
    """Slide-by-slide content for an Instagram carousel."""

    slides: list[str] = field(default_factory=list)
    caption: str = ""       # main caption for the first slide
    hashtags: str = ""

    @property
    def slide_count(self) -> int:
        return len(self.slides)

    def to_text(self) -> str:
        lines = [f"=== CAROUSEL ({self.slide_count} slides) ===\n"]
        for i, slide in enumerate(self.slides, 1):
            lines.append(f"--- Slide {i} ---\n{slide}\n")
        if self.hashtags:
            lines.append(f"--- Hashtags ---\n{self.hashtags}")
        return "\n".join(lines)


@dataclass
class XThread:
    """A numbered X/Twitter thread."""

    tweets: list[str] = field(default_factory=list)

    @property
    def tweet_count(self) -> int:
        return len(self.tweets)

    def to_text(self) -> str:
        lines = [f"=== THREAD ({self.tweet_count} tweets) ===\n"]
        for i, tweet in enumerate(self.tweets, 1):
            lines.append(f"[{i}/{self.tweet_count}]\n{tweet}\n")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


class ContentFormatter:
    """Format a ContentDraft body for a specific publishing platform."""

    # Typical word counts per output unit
    WORDS_PER_SLIDE = 40
    WORDS_PER_TWEET = 40

    def format_instagram(self, draft: ContentDraft) -> InstagramCarousel:
        """Split the draft body into carousel slides."""
        paragraphs = _split_paragraphs(draft.body)
        slides: list[str] = []

        # Slide 1 — hook (title / first paragraph)
        hook = _make_hook(draft.title, paragraphs)
        slides.append(hook)

        # Middle slides — body paragraphs
        for para in paragraphs[1:]:
            sentences = _split_sentences(para)
            chunk = ""
            for sent in sentences:
                if len(chunk) + len(sent) > 220:
                    if chunk:
                        slides.append(chunk.strip())
                    chunk = sent
                else:
                    chunk = (chunk + " " + sent).strip() if chunk else sent
            if chunk:
                slides.append(chunk.strip())

        # Last slide — CTA
        slides.append(_make_cta(draft))

        # Trim empty slides
        slides = [s for s in slides if s.strip()]

        # Limit to 10 slides (Instagram max for carousels)
        if len(slides) > 10:
            slides = slides[:9] + [slides[-1]]

        hashtags = _build_hashtags(draft.tags)
        caption = f"{slides[0]}\n\n{hashtags}"[:INSTAGRAM_CAPTION_LIMIT]

        return InstagramCarousel(slides=slides, caption=caption, hashtags=hashtags)

    def format_x_thread(self, draft: ContentDraft) -> XThread:
        """Format the draft as a Twitter/X thread."""
        paragraphs = _split_paragraphs(draft.body)
        tweets: list[str] = []

        # Tweet 1: hook
        hook_text = f"🧵 {draft.title}"
        tweets.append(hook_text[:X_TWEET_LIMIT])

        # Middle tweets
        for para in paragraphs:
            sentences = _split_sentences(para)
            chunk = ""
            for sent in sentences:
                candidate = (chunk + " " + sent).strip() if chunk else sent
                if len(candidate) > X_TWEET_LIMIT - 10:
                    if chunk:
                        tweets.append(chunk.strip())
                    chunk = sent
                else:
                    chunk = candidate
            if chunk:
                tweets.append(chunk.strip())

        # Final tweet: source
        if draft.source_url:
            tweets.append(f"📰 Fonte: {draft.source_url}"[:X_TWEET_LIMIT])

        # Number the tweets
        n = len(tweets)
        numbered = []
        for i, tweet in enumerate(tweets, 1):
            prefix = f"[{i}/{n}] "
            numbered.append((prefix + tweet)[: X_TWEET_LIMIT])

        return XThread(tweets=numbered)

    def format_threads_post(self, draft: ContentDraft) -> str:
        """Single Threads post (≤ 500 chars)."""
        text = f"{draft.title}\n\n{_first_paragraph(draft.body)}"
        if len(text) > THREADS_POST_LIMIT:
            text = text[: THREADS_POST_LIMIT - 3] + "..."
        return text

    def format_newsletter_section(self, draft: ContentDraft) -> str:
        """Markdown fragment for a newsletter section."""
        lines = [
            f"## {draft.title}",
            "",
            draft.body,
        ]
        if draft.source_url:
            lines += ["", f"> 📰 *Fonte: [{draft.source_name or draft.source_url}]({draft.source_url})*"]
        tags_str = " ".join(f"`#{t}`" for t in draft.tags[:6])
        if tags_str:
            lines += ["", tags_str]
        return "\n".join(lines)

    def format(self, draft: ContentDraft, platform: Platform) -> str:
        """Dispatch to the appropriate formatter and return plain text."""
        if platform == Platform.INSTAGRAM:
            return self.format_instagram(draft).to_text()
        if platform == Platform.X:
            return self.format_x_thread(draft).to_text()
        if platform == Platform.THREADS:
            return self.format_threads_post(draft)
        if platform == Platform.NEWSLETTER:
            return self.format_newsletter_section(draft)
        # Default: plain body
        return draft.body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines; strip markdown headers."""
    paragraphs = []
    for para in re.split(r"\n{2,}", text.strip()):
        cleaned = re.sub(r"^\s*#{1,4}\s*", "", para).strip()
        if cleaned:
            paragraphs.append(cleaned)
    return paragraphs


def _split_sentences(text: str) -> list[str]:
    """Naive sentence splitter (handles PT-BR abbreviations imperfectly)."""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _first_paragraph(text: str) -> str:
    paras = _split_paragraphs(text)
    return paras[0] if paras else text[:200]


def _make_hook(title: str, paragraphs: list[str]) -> str:
    first = paragraphs[0] if paragraphs else ""
    hook = f"📌 {title}\n\n{first}"
    return hook[:220]


def _make_cta(draft: ContentDraft) -> str:
    ctas = {
        ContentType.NEWS_SUMMARY: "💬 O que você acha deste assunto?\nSalve para ver mais conteúdos sobre política brasileira.",
        ContentType.INSTITUTION_EXPLAINER: "📚 Conheceu a instituição hoje? Compartilhe com quem precisa entender o Brasil!",
        ContentType.FIGURE_PROFILE: "🔍 Quer saber mais sobre esta figura pública? Siga para mais perfis.",
        ContentType.TIMELINE: "📅 A história importa. Compartilhe esta linha do tempo!",
        ContentType.CONCEPT_EXPLAINER: "❓ Ficou com dúvidas? Manda nos comentários!",
    }
    return ctas.get(draft.content_type, "📲 Siga para mais conteúdo sobre o Brasil.")


def _build_hashtags(tags: list[str], max_tags: int = 15) -> str:
    core = ["#politicabrasileira", "#brasil", "#cidadania", "#democracia"]
    extra = [f"#{t.replace(' ', '').lower()}" for t in tags[:max_tags]]
    all_tags = core + [t for t in extra if t not in core]
    return " ".join(all_tags[:max_tags])
