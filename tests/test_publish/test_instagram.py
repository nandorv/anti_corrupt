"""
Tests for src/publish/instagram.py

All HTTP calls are mocked — no real API credentials needed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.publish.instagram import InstagramClient, InstagramError


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_client(account_id: str = "ACC123") -> InstagramClient:
    """Return a client with a dummy token/account and mocked httpx."""
    client = InstagramClient(
        access_token="TOKEN",
        account_id=account_id,
        base_url="https://graph.facebook.com/v19.0",
    )
    return client


def _ok_response(payload: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = payload
    return mock


def _err_response(message: str) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"error": {"message": message}}
    return mock


# ---------------------------------------------------------------------------
# create_image_container
# ---------------------------------------------------------------------------


class TestCreateImageContainer:
    def test_returns_container_id(self) -> None:
        client = _make_client()
        client._http.post = MagicMock(return_value=_ok_response({"id": "CONTAINER1"}))

        result = client.create_image_container("https://example.com/img.jpg", "Caption")

        assert result == "CONTAINER1"

    def test_payload_includes_caption_for_standalone(self) -> None:
        client = _make_client()
        client._http.post = MagicMock(return_value=_ok_response({"id": "C1"}))

        client.create_image_container("https://example.com/img.jpg", "My Caption")

        call_kwargs = client._http.post.call_args
        data = call_kwargs[1]["data"] if "data" in call_kwargs[1] else call_kwargs[0][1]
        assert data["caption"] == "My Caption"

    def test_carousel_item_sets_flag_not_caption(self) -> None:
        client = _make_client()
        client._http.post = MagicMock(return_value=_ok_response({"id": "C2"}))

        client.create_image_container(
            "https://example.com/img.jpg", is_carousel_item=True
        )

        call_kwargs = client._http.post.call_args
        data = call_kwargs[1]["data"] if "data" in call_kwargs[1] else call_kwargs[0][1]
        assert data.get("is_carousel_item") == "true"
        assert "caption" not in data

    def test_raises_instagram_error_on_api_error(self) -> None:
        client = _make_client()
        client._http.post = MagicMock(return_value=_err_response("Invalid token"))

        with pytest.raises(InstagramError, match="Invalid token"):
            client.create_image_container("https://example.com/img.jpg")


# ---------------------------------------------------------------------------
# create_carousel_container
# ---------------------------------------------------------------------------


class TestCreateCarouselContainer:
    def test_returns_container_id(self) -> None:
        client = _make_client()
        client._http.post = MagicMock(return_value=_ok_response({"id": "CAROUSEL1"}))

        result = client.create_carousel_container(["C1", "C2", "C3"], "Caption")

        assert result == "CAROUSEL1"

    def test_children_joined_as_csv(self) -> None:
        client = _make_client()
        client._http.post = MagicMock(return_value=_ok_response({"id": "X"}))

        client.create_carousel_container(["A", "B", "C"], "Cap")

        call_kwargs = client._http.post.call_args
        data = call_kwargs[1]["data"] if "data" in call_kwargs[1] else call_kwargs[0][1]
        assert data["children"] == "A,B,C"
        assert data["media_type"] == "CAROUSEL"


# ---------------------------------------------------------------------------
# publish_container
# ---------------------------------------------------------------------------


class TestPublishContainer:
    def test_returns_post_id(self) -> None:
        client = _make_client()
        client._http.post = MagicMock(return_value=_ok_response({"id": "POST123"}))

        result = client.publish_container("CONTAINER1")

        assert result == "POST123"

    def test_raises_on_error(self) -> None:
        client = _make_client()
        client._http.post = MagicMock(return_value=_err_response("Rate limit exceeded"))

        with pytest.raises(InstagramError, match="Rate limit"):
            client.publish_container("CONTAINER1")


# ---------------------------------------------------------------------------
# post_image (high-level)
# ---------------------------------------------------------------------------


class TestPostImage:
    def test_creates_container_then_publishes(self) -> None:
        client = _make_client()
        responses = [
            _ok_response({"id": "CONTAINER1"}),  # create_image_container
            _ok_response({"id": "POST1"}),        # publish_container
        ]
        client._http.post = MagicMock(side_effect=responses)

        with patch("time.sleep"):
            result = client.post_image("https://example.com/img.jpg", "Caption")

        assert result == "POST1"
        assert client._http.post.call_count == 2


# ---------------------------------------------------------------------------
# post_carousel (high-level)
# ---------------------------------------------------------------------------


class TestPostCarousel:
    def test_creates_children_then_parent_then_publishes(self) -> None:
        client = _make_client()
        responses = [
            _ok_response({"id": "CHILD1"}),    # slide 1
            _ok_response({"id": "CHILD2"}),    # slide 2
            _ok_response({"id": "PARENT1"}),   # carousel container
            _ok_response({"id": "POST1"}),     # publish
        ]
        client._http.post = MagicMock(side_effect=responses)

        with patch("time.sleep"):
            result = client.post_carousel(
                ["https://example.com/s1.jpg", "https://example.com/s2.jpg"],
                caption="My carousel",
            )

        assert result == "POST1"
        assert client._http.post.call_count == 4

    def test_raises_on_empty_urls(self) -> None:
        client = _make_client()
        with pytest.raises(ValueError, match="at least one"):
            client.post_carousel([], caption="Empty")

    def test_raises_on_too_many_images(self) -> None:
        client = _make_client()
        with pytest.raises(ValueError, match="at most 10"):
            client.post_carousel(
                [f"https://example.com/{i}.jpg" for i in range(11)],
                caption="Too many",
            )


# ---------------------------------------------------------------------------
# get_media_insights
# ---------------------------------------------------------------------------


class TestGetMediaInsights:
    def test_returns_metrics_dict(self) -> None:
        client = _make_client()
        client._http.get = MagicMock(
            return_value=_ok_response(
                {
                    "data": [
                        {"name": "impressions", "values": [{"value": 1500}]},
                        {"name": "reach", "values": [{"value": 1100}]},
                        {"name": "likes", "values": [{"value": 87}]},
                    ]
                }
            )
        )

        result = client.get_media_insights("POST123")

        assert result["impressions"] == 1500
        assert result["reach"] == 1100
        assert result["likes"] == 87

    def test_raises_on_api_error(self) -> None:
        client = _make_client()
        client._http.get = MagicMock(return_value=_err_response("Insufficient permissions"))

        with pytest.raises(InstagramError, match="Insufficient permissions"):
            client.get_media_insights("POST123")
