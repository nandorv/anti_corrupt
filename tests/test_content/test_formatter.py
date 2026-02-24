"""Tests for src/content/formatter.py — platform content formatters."""

from __future__ import annotations

import pytest

from src.content.formatter import (
    INSTAGRAM_CAPTION_LIMIT,
    THREADS_POST_LIMIT,
    X_TWEET_LIMIT,
    ContentFormatter,
    InstagramCarousel,
    XThread,
)
from src.content.models import ContentDraft, ContentStatus, ContentType, Platform


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_draft(
    title: str = "O que é o Supremo Tribunal Federal?",
    body: str = None,
    source_url: str = "https://example.com/stf",
    source_name: str = "Agência Brasil",
    tags: list[str] | None = None,
    content_type: ContentType = ContentType.INSTITUTION_EXPLAINER,
) -> ContentDraft:
    if body is None:
        body = (
            "O Supremo Tribunal Federal (STF) é o órgão de cúpula do Poder Judiciário "
            "brasileiro e o guardião da Constituição Federal.\n\n"
            "Composto por onze ministros nomeados pelo Presidente da República, o STF "
            "tem competência para julgar ações de inconstitucionalidade e proteger "
            "direitos fundamentais dos cidadãos.\n\n"
            "O tribunal foi criado em 1891 e desde então desempenha papel central na "
            "democracia brasileira, garantindo o equilíbrio entre os três poderes.\n\n"
            "Entre suas atribuições está o julgamento do Presidente da República, "
            "vice-presidente e membros do Congresso por crimes comuns."
        )
    return ContentDraft(
        title=title,
        body=body,
        content_type=content_type,
        status=ContentStatus.DRAFT,
        source_url=source_url,
        source_name=source_name,
        tags=tags or ["stf", "judiciário", "constituição"],
    )


@pytest.fixture
def formatter() -> ContentFormatter:
    return ContentFormatter()


@pytest.fixture
def draft() -> ContentDraft:
    return _make_draft()


# ---------------------------------------------------------------------------
# InstagramCarousel
# ---------------------------------------------------------------------------


class TestFormatInstagram:
    def test_returns_instagram_carousel(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_instagram(draft)
        assert isinstance(result, InstagramCarousel)

    def test_has_at_least_two_slides(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_instagram(draft)
        assert result.slide_count >= 2

    def test_first_slide_contains_title(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_instagram(draft)
        assert draft.title in result.slides[0] or "STF" in result.slides[0]

    def test_no_more_than_ten_slides(self, formatter: ContentFormatter, draft: ContentDraft):
        # Generate a very long draft
        long_body = "Parágrafo de texto longo. " * 30 + "\n\n" * 15
        long_draft = _make_draft(body=long_body)
        result = formatter.format_instagram(long_draft)
        assert result.slide_count <= 10

    def test_caption_within_limit(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_instagram(draft)
        assert len(result.caption) <= INSTAGRAM_CAPTION_LIMIT

    def test_hashtags_present(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_instagram(draft)
        assert result.hashtags != ""

    def test_to_text_includes_slide_markers(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_instagram(draft)
        text = result.to_text()
        assert "Slide 1" in text
        assert "CAROUSEL" in text

    def test_empty_slides_removed(self, formatter: ContentFormatter):
        minimal_draft = _make_draft(body="Uma frase simples sobre política.")
        result = formatter.format_instagram(minimal_draft)
        for slide in result.slides:
            assert slide.strip() != ""


# ---------------------------------------------------------------------------
# XThread
# ---------------------------------------------------------------------------


class TestFormatXThread:
    def test_returns_x_thread(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_x_thread(draft)
        assert isinstance(result, XThread)

    def test_has_at_least_two_tweets(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_x_thread(draft)
        assert result.tweet_count >= 2

    def test_all_tweets_within_limit(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_x_thread(draft)
        for tweet in result.tweets:
            assert len(tweet) <= X_TWEET_LIMIT, f"Tweet too long: {tweet!r}"

    def test_first_tweet_contains_title(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_x_thread(draft)
        assert "STF" in result.tweets[0] or draft.title[:20] in result.tweets[0]

    def test_tweets_are_numbered(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_x_thread(draft)
        # First tweet should have a [1/N] prefix
        assert result.tweets[0].startswith("[1/")

    def test_source_url_in_last_tweet(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_x_thread(draft)
        last_tweet = result.tweets[-1]
        assert "example.com" in last_tweet or "Fonte" in last_tweet

    def test_to_text_includes_thread_marker(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_x_thread(draft)
        assert "THREAD" in result.to_text()

    def test_draft_without_source_url(self, formatter: ContentFormatter):
        draft = _make_draft(source_url=None)
        draft.source_url = None
        result = formatter.format_x_thread(draft)
        # Should not crash — just no source tweet at end
        assert isinstance(result, XThread)


# ---------------------------------------------------------------------------
# Threads post
# ---------------------------------------------------------------------------


class TestFormatThreadsPost:
    def test_returns_string(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_threads_post(draft)
        assert isinstance(result, str)

    def test_within_char_limit(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_threads_post(draft)
        assert len(result) <= THREADS_POST_LIMIT

    def test_contains_title(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_threads_post(draft)
        assert draft.title[:20] in result

    def test_long_text_truncated(self, formatter: ContentFormatter):
        long_draft = _make_draft(
            title="A" * 100,
            body="B" * 1000,
        )
        result = formatter.format_threads_post(long_draft)
        assert len(result) <= THREADS_POST_LIMIT
        assert result.endswith("...")


# ---------------------------------------------------------------------------
# Newsletter section
# ---------------------------------------------------------------------------


class TestFormatNewsletterSection:
    def test_returns_string(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_newsletter_section(draft)
        assert isinstance(result, str)

    def test_contains_h2_title(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_newsletter_section(draft)
        assert f"## {draft.title}" in result

    def test_contains_body(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_newsletter_section(draft)
        assert "Supremo" in result

    def test_contains_source_link(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_newsletter_section(draft)
        assert "example.com/stf" in result

    def test_contains_tags(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format_newsletter_section(draft)
        assert "#stf" in result or "`#stf`" in result

    def test_no_source_link_when_url_absent(self, formatter: ContentFormatter):
        draft = _make_draft(source_url=None)
        draft.source_url = None
        result = formatter.format_newsletter_section(draft)
        # Should not crash and should not contain "None"
        assert "None" not in result


# ---------------------------------------------------------------------------
# Dispatch: format()
# ---------------------------------------------------------------------------


class TestFormatDispatch:
    def test_dispatch_instagram(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format(draft, Platform.INSTAGRAM)
        assert "CAROUSEL" in result

    def test_dispatch_x(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format(draft, Platform.X)
        assert "THREAD" in result

    def test_dispatch_threads(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format(draft, Platform.THREADS)
        assert isinstance(result, str)
        assert len(result) <= THREADS_POST_LIMIT

    def test_dispatch_newsletter(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format(draft, Platform.NEWSLETTER)
        assert f"## {draft.title}" in result

    def test_dispatch_web_returns_body(self, formatter: ContentFormatter, draft: ContentDraft):
        result = formatter.format(draft, Platform.WEB)
        assert result == draft.body
