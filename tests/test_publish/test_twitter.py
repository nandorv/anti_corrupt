"""
Tests for src/publish/twitter.py

Tweepy internals are mocked — no real API credentials needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.publish.twitter import TweetResult, TwitterClient, TwitterError


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_client() -> TwitterClient:
    return TwitterClient(
        api_key="KEY",
        api_secret="SECRET",
        access_token="AT",
        access_secret="AS",
        bearer_token="BT",
    )


@dataclass
class _FakeTweetResponse:
    data: dict


@dataclass
class _FakeTweetData:
    id: str

    def get(self, key: str, default: Any = None) -> Any:
        return {"id": self.id}.get(key, default)


def _fake_create_tweet(**kwargs: Any) -> _FakeTweetResponse:
    return _FakeTweetResponse(data={"id": "TWEET123"})


# ---------------------------------------------------------------------------
# post_tweet
# ---------------------------------------------------------------------------


class TestPostTweet:
    def test_returns_tweet_result(self) -> None:
        client = _make_client()

        mock_v2 = MagicMock()
        mock_v2.create_tweet.return_value = _FakeTweetResponse(data={"id": "T1"})
        client._client = mock_v2

        result = client.post_tweet("Hello, world!")

        assert isinstance(result, TweetResult)
        assert result.tweet_id == "T1"
        assert "T1" in result.url

    def test_passes_text_to_api(self) -> None:
        client = _make_client()
        mock_v2 = MagicMock()
        mock_v2.create_tweet.return_value = _FakeTweetResponse(data={"id": "T1"})
        client._client = mock_v2

        client.post_tweet("My tweet text")

        kwargs = mock_v2.create_tweet.call_args[1]
        assert kwargs["text"] == "My tweet text"

    def test_passes_media_ids_when_given(self, tmp_path: Path) -> None:
        client = _make_client()

        mock_v2 = MagicMock()
        mock_v2.create_tweet.return_value = _FakeTweetResponse(data={"id": "T2"})
        client._client = mock_v2

        # Stub upload_media so it doesn't actually call the v1.1 API
        client.upload_media = MagicMock(return_value="MEDIA1")  # type: ignore[method-assign]

        img = tmp_path / "test.png"
        img.write_bytes(b"PNG")

        result = client.post_tweet("With image", media_paths=[img])

        assert result.media_ids == ["MEDIA1"]
        kwargs = mock_v2.create_tweet.call_args[1]
        assert kwargs["media_ids"] == ["MEDIA1"]

    def test_passes_reply_to_id(self) -> None:
        client = _make_client()
        mock_v2 = MagicMock()
        mock_v2.create_tweet.return_value = _FakeTweetResponse(data={"id": "T3"})
        client._client = mock_v2

        client.post_tweet("Reply tweet", reply_to_id="PARENT123")

        kwargs = mock_v2.create_tweet.call_args[1]
        assert kwargs["in_reply_to_tweet_id"] == "PARENT123"

    def test_raises_twitter_error_on_exception(self) -> None:
        client = _make_client()
        mock_v2 = MagicMock()
        mock_v2.create_tweet.side_effect = Exception("Forbidden")
        client._client = mock_v2

        with pytest.raises(TwitterError, match="Forbidden"):
            client.post_tweet("Failing tweet")


# ---------------------------------------------------------------------------
# post_thread
# ---------------------------------------------------------------------------


class TestPostThread:
    def test_chains_tweets_as_replies(self) -> None:
        client = _make_client()
        tweet_ids = iter(["T1", "T2", "T3"])
        mock_v2 = MagicMock()
        mock_v2.create_tweet.side_effect = lambda **kw: _FakeTweetResponse(
            data={"id": next(tweet_ids)}
        )
        client._client = mock_v2

        results = client.post_thread(["First", "Second", "Third"])

        assert len(results) == 3
        assert results[0].tweet_id == "T1"
        assert results[1].tweet_id == "T2"
        assert results[2].tweet_id == "T3"

        # Each tweet after the first should reply to the previous
        calls = mock_v2.create_tweet.call_args_list
        assert "in_reply_to_tweet_id" not in calls[0][1]
        assert calls[1][1]["in_reply_to_tweet_id"] == "T1"
        assert calls[2][1]["in_reply_to_tweet_id"] == "T2"

    def test_raises_on_empty_list(self) -> None:
        client = _make_client()
        with pytest.raises(ValueError, match="at least one"):
            client.post_thread([])


# ---------------------------------------------------------------------------
# get_tweet_metrics
# ---------------------------------------------------------------------------


class TestGetTweetMetrics:
    def test_returns_public_metrics(self) -> None:
        client = _make_client()
        mock_v2 = MagicMock()
        mock_data = MagicMock()
        mock_data.get.return_value = {
            "like_count": 42,
            "retweet_count": 10,
            "reply_count": 5,
        }
        mock_v2.get_tweet.return_value = MagicMock(data=mock_data)
        client._client = mock_v2

        metrics = client.get_tweet_metrics("TWEET123")

        assert metrics["like_count"] == 42
        assert metrics["retweet_count"] == 10

    def test_raises_on_api_error(self) -> None:
        client = _make_client()
        mock_v2 = MagicMock()
        mock_v2.get_tweet.side_effect = Exception("Unauthorized")
        client._client = mock_v2

        with pytest.raises(TwitterError, match="Unauthorized"):
            client.get_tweet_metrics("TWEET123")


# ---------------------------------------------------------------------------
# tweepy unavailable
# ---------------------------------------------------------------------------


class TestTweepyUnavailable:
    def test_raises_when_tweepy_missing(self) -> None:
        with patch("src.publish.twitter._TWEEPY_AVAILABLE", False):
            client = TwitterClient(
                api_key="K", api_secret="S", access_token="AT", access_secret="AS"
            )
            # Force re-check by clearing cached instances
            client._client = None
            with pytest.raises(TwitterError, match="tweepy is not installed"):
                client._get_client()
