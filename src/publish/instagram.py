"""
Instagram Graph API publishing client.

Docs: https://developers.facebook.com/docs/instagram-api/guides/content-publishing
Rate limits: 50 API calls/hour, 25 posts per 24-hour period

Required settings:
  INSTAGRAM_ACCESS_TOKEN          — long-lived user access token
  INSTAGRAM_BUSINESS_ACCOUNT_ID  — Instagram Business / Creator account ID

Flow (single image):
  1. POST /{user_id}/media              → container_id
  2. POST /{user_id}/media_publish      → post_id

Flow (carousel — up to 10 images):
  1. POST /{user_id}/media for each image (is_carousel_item=true)  → child_ids
  2. POST /{user_id}/media with CAROUSEL + children=[child_ids]    → parent_id
  3. POST /{user_id}/media_publish with creation_id=parent_id      → post_id
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.facebook.com/v19.0"
_CAROUSEL_MAX = 10


class InstagramError(Exception):
    """Raised when the Instagram Graph API returns an error response."""


class InstagramClient:
    """
    Thin wrapper around the Instagram Content Publishing API.

    Usage::

        client = InstagramClient()
        post_id = client.post_image("https://example.com/img.jpg", "Caption here")
        post_id = client.post_carousel(
            ["https://example.com/slide1.jpg", "https://example.com/slide2.jpg"],
            caption="My carousel",
        )
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        account_id: Optional[str] = None,
        *,
        base_url: str = _GRAPH_BASE,
        timeout: float = 30.0,
    ) -> None:
        from config.settings import settings

        self.token = access_token or settings.instagram_access_token
        self.account_id = account_id or settings.instagram_business_account_id
        self._http = httpx.Client(base_url=base_url, timeout=timeout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post(self, path: str, data: dict) -> dict:
        """POST to the Graph API and return parsed JSON, raising on error."""
        data["access_token"] = self.token
        resp = self._http.post(path, data=data)
        body = resp.json()
        if "error" in body:
            msg = body["error"].get("message", str(body["error"]))
            raise InstagramError(msg)
        return body

    def _get(self, path: str, params: dict) -> dict:
        params["access_token"] = self.token
        resp = self._http.get(path, params=params)
        body = resp.json()
        if "error" in body:
            msg = body["error"].get("message", str(body["error"]))
            raise InstagramError(msg)
        return body

    # ------------------------------------------------------------------
    # Container creation
    # ------------------------------------------------------------------

    def create_image_container(
        self,
        image_url: str,
        caption: str = "",
        *,
        is_carousel_item: bool = False,
    ) -> str:
        """
        Create a single-image media container.

        Returns the container_id (not yet published).
        """
        payload: dict = {"image_url": image_url}
        if is_carousel_item:
            payload["is_carousel_item"] = "true"
        else:
            payload["caption"] = caption

        body = self._post(f"/{self.account_id}/media", payload)
        container_id: str = body["id"]
        logger.info("Created image container: %s", container_id)
        return container_id

    def create_carousel_container(
        self,
        children_ids: list[str],
        caption: str = "",
    ) -> str:
        """
        Create a carousel parent container from existing child containers.

        Returns the parent container_id.
        """
        payload = {
            "media_type": "CAROUSEL",
            "caption": caption,
            "children": ",".join(children_ids),
        }
        body = self._post(f"/{self.account_id}/media", payload)
        container_id: str = body["id"]
        logger.info("Created carousel container: %s (%d children)", container_id, len(children_ids))
        return container_id

    def publish_container(self, container_id: str) -> str:
        """
        Publish a previously created media container.

        Returns the media_id (the published post's ID).
        """
        body = self._post(
            f"/{self.account_id}/media_publish",
            {"creation_id": container_id},
        )
        post_id: str = body["id"]
        logger.info("Published container %s → post %s", container_id, post_id)
        return post_id

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    def post_image(
        self,
        image_url: str,
        caption: str,
        *,
        delay_seconds: float = 1.0,
    ) -> str:
        """
        Create and publish a single-image post in one call.

        Returns the post_id.
        """
        container_id = self.create_image_container(image_url, caption)
        time.sleep(delay_seconds)
        return self.publish_container(container_id)

    def post_carousel(
        self,
        image_urls: list[str],
        caption: str,
        *,
        delay_seconds: float = 1.0,
    ) -> str:
        """
        Create and publish a carousel post (2–10 images).

        Returns the post_id.
        """
        if not image_urls:
            raise ValueError("Carousel requires at least one image URL.")
        if len(image_urls) > _CAROUSEL_MAX:
            raise ValueError(
                f"Instagram carousels support at most {_CAROUSEL_MAX} images "
                f"(got {len(image_urls)})."
            )

        children: list[str] = []
        for url in image_urls:
            child_id = self.create_image_container(url, is_carousel_item=True)
            children.append(child_id)
            time.sleep(delay_seconds)

        parent_id = self.create_carousel_container(children, caption)
        time.sleep(delay_seconds)
        return self.publish_container(parent_id)

    # ------------------------------------------------------------------
    # Insights / Analytics
    # ------------------------------------------------------------------

    def get_media_insights(
        self,
        media_id: str,
        metrics: tuple[str, ...] = (
            "impressions",
            "reach",
            "likes",
            "comments",
            "saved",
            "shares",
        ),
    ) -> dict[str, int]:
        """
        Fetch performance metrics for a published post.

        Returns a dict like ``{"impressions": 1200, "reach": 950, ...}``.
        """
        body = self._get(
            f"/{media_id}/insights",
            {"metric": ",".join(metrics)},
        )
        result: dict[str, int] = {}
        for item in body.get("data", []):
            values = item.get("values") or [{}]
            result[item["name"]] = values[0].get("value", 0)
        return result

    # ------------------------------------------------------------------
    # Context manager / cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "InstagramClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
