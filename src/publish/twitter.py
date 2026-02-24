"""
X/Twitter API v2 publishing client using Tweepy.

Docs: https://docs.tweepy.org/en/stable/
Rate limits:
  Free tier  : 1,500 tweets/month (write only)
  Basic tier ($100/mo): 3,000 tweets/month write, 10,000 reads/month

Required settings:
  TWITTER_API_KEY, TWITTER_API_SECRET
  TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
  TWITTER_BEARER_TOKEN

Note: Media upload still requires Twitter API v1.1 (tweepy.API).
      Tweet creation uses v2 (tweepy.Client).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional tweepy import — publishing degrades gracefully if not installed
# ---------------------------------------------------------------------------

try:
    import tweepy as _tweepy  # noqa: F401

    _TWEEPY_AVAILABLE = True
except ImportError:
    _TWEEPY_AVAILABLE = False

if TYPE_CHECKING:
    import tweepy


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TweetResult:
    """Result of a successful tweet creation."""

    tweet_id: str
    text: str
    url: str = ""
    media_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TwitterError(Exception):
    """Raised when the X/Twitter API returns an error."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class TwitterClient:
    """
    Thin wrapper around the X/Twitter API v2 via Tweepy.

    Usage::

        client = TwitterClient()
        result = client.post_tweet("Hello, world!")
        results = client.post_thread(["First tweet", "Second tweet", "Third tweet"])
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        access_secret: Optional[str] = None,
        bearer_token: Optional[str] = None,
    ) -> None:
        from config.settings import settings

        self._api_key = api_key or settings.twitter_api_key
        self._api_secret = api_secret or settings.twitter_api_secret
        self._access_token = access_token or settings.twitter_access_token
        self._access_secret = access_secret or settings.twitter_access_secret
        self._bearer_token = bearer_token or settings.twitter_bearer_token

        self._client: Optional["tweepy.Client"] = None
        self._v1_api: Optional["tweepy.API"] = None

    # ------------------------------------------------------------------
    # Lazy API initialisation
    # ------------------------------------------------------------------

    def _get_client(self) -> "tweepy.Client":
        """Return (or create) the Tweepy v2 Client."""
        if not _TWEEPY_AVAILABLE:
            raise TwitterError(
                "tweepy is not installed. Run: uv add tweepy"
            )
        if self._client is None:
            import tweepy

            self._client = tweepy.Client(
                consumer_key=self._api_key,
                consumer_secret=self._api_secret,
                access_token=self._access_token,
                access_token_secret=self._access_secret,
                bearer_token=self._bearer_token,
                wait_on_rate_limit=True,
            )
        return self._client

    def _get_v1_api(self) -> "tweepy.API":
        """Return (or create) the Tweepy v1.1 API (needed for media uploads)."""
        if not _TWEEPY_AVAILABLE:
            raise TwitterError(
                "tweepy is not installed. Run: uv add tweepy"
            )
        if self._v1_api is None:
            import tweepy

            auth = tweepy.OAuth1UserHandler(
                self._api_key,
                self._api_secret,
                self._access_token,
                self._access_secret,
            )
            self._v1_api = tweepy.API(auth, wait_on_rate_limit=True)
        return self._v1_api

    # ------------------------------------------------------------------
    # Media upload
    # ------------------------------------------------------------------

    def upload_media(self, image_path: Path) -> str:
        """
        Upload an image file via the v1.1 media endpoint.

        Returns the media_id_string to attach to a tweet.
        """
        api = self._get_v1_api()
        try:
            media = api.media_upload(str(image_path))
            media_id: str = media.media_id_string
            logger.info("Uploaded media %s → %s", image_path.name, media_id)
            return media_id
        except Exception as exc:
            raise TwitterError(f"Media upload failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Tweet / thread
    # ------------------------------------------------------------------

    def post_tweet(
        self,
        text: str,
        media_paths: Optional[list[Path]] = None,
        reply_to_id: Optional[str] = None,
    ) -> TweetResult:
        """
        Create a tweet, optionally attaching images and/or as a reply.

        Args:
            text:          Tweet text (max 280 chars).
            media_paths:   Local image files to attach (max 4).
            reply_to_id:   Tweet ID to reply to (for threading).

        Returns:
            TweetResult with tweet_id, url, and attached media_ids.
        """
        client = self._get_client()

        media_ids: list[str] = []
        if media_paths:
            media_ids = [self.upload_media(p) for p in media_paths]

        kwargs: dict = {"text": text}
        if media_ids:
            kwargs["media_ids"] = media_ids
        if reply_to_id:
            kwargs["in_reply_to_tweet_id"] = reply_to_id

        try:
            response = client.create_tweet(**kwargs)
            tweet_id = str(response.data["id"])
            url = f"https://x.com/i/web/status/{tweet_id}"
            logger.info("Posted tweet %s", tweet_id)
            return TweetResult(tweet_id=tweet_id, text=text, url=url, media_ids=media_ids)
        except Exception as exc:
            raise TwitterError(f"Tweet creation failed: {exc}") from exc

    def post_thread(
        self,
        tweets: list[str],
        media_paths: Optional[list[Optional[list[Path]]]] = None,
    ) -> list[TweetResult]:
        """
        Post a chain of tweets as a thread.

        Args:
            tweets:       List of tweet texts (first is the root).
            media_paths:  Per-tweet optional list of image paths.
                          e.g. [[Path("img1.jpg")], None, [Path("img3.jpg")]]

        Returns:
            List of TweetResult in posting order.
        """
        if not tweets:
            raise ValueError("Thread requires at least one tweet.")

        results: list[TweetResult] = []
        reply_to: Optional[str] = None

        for i, text in enumerate(tweets):
            paths: Optional[list[Path]] = None
            if media_paths and i < len(media_paths):
                paths = media_paths[i]

            result = self.post_tweet(text, media_paths=paths, reply_to_id=reply_to)
            results.append(result)
            reply_to = result.tweet_id

        logger.info("Posted thread: %d tweets, root=%s", len(results), results[0].tweet_id)
        return results

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_tweet_metrics(self, tweet_id: str) -> dict[str, int]:
        """
        Fetch public metrics for a tweet (likes, retweets, replies, impressions).

        Returns a dict like ``{"like_count": 42, "retweet_count": 10, ...}``.
        """
        client = self._get_client()
        try:
            response = client.get_tweet(
                tweet_id,
                tweet_fields=["public_metrics", "created_at"],
            )
            if response.data:
                metrics = response.data.get("public_metrics") or {}
                return {k: int(v) for k, v in metrics.items()}
        except Exception as exc:
            raise TwitterError(f"Failed to fetch metrics for {tweet_id}: {exc}") from exc
        return {}
