"""
Tests for src/publish/scheduler.py
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from src.publish.scheduler import PostScheduler, ScheduledPost


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def scheduler(tmp_path: Path) -> PostScheduler:
    return PostScheduler(tmp_path / "sched.db")


def _future(minutes: int = 60) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)


def _past(minutes: int = 5) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)


def _make_post(**kwargs) -> ScheduledPost:
    defaults = dict(
        draft_id="draft1",
        platform="instagram",
        scheduled_at=_future(),
        image_urls=["https://example.com/img.jpg"],
        caption="Test caption",
    )
    defaults.update(kwargs)
    return ScheduledPost(**defaults)


# ---------------------------------------------------------------------------
# ScheduledPost model
# ---------------------------------------------------------------------------


class TestScheduledPostModel:
    def test_auto_generates_id(self) -> None:
        post = _make_post()
        assert len(post.id) == 8

    def test_explicit_id_preserved(self) -> None:
        post = ScheduledPost(
            id="myid",
            draft_id="d1",
            platform="twitter",
            scheduled_at=_future(),
        )
        assert post.id == "myid"

    def test_invalid_platform_raises(self) -> None:
        with pytest.raises(ValueError, match="platform"):
            ScheduledPost(draft_id="d1", platform="tiktok", scheduled_at=_future())

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValueError, match="status"):
            ScheduledPost(
                draft_id="d1", platform="twitter", scheduled_at=_future(), status="queued"
            )

    def test_is_due_false_for_future(self) -> None:
        post = _make_post(scheduled_at=_future(60))
        assert post.is_due is False

    def test_is_due_true_for_past(self) -> None:
        post = _make_post(scheduled_at=_past(5))
        assert post.is_due is True

    def test_is_due_false_for_non_pending_status(self) -> None:
        post = _make_post(scheduled_at=_past(5), status="done")
        assert post.is_due is False


# ---------------------------------------------------------------------------
# PostScheduler CRUD
# ---------------------------------------------------------------------------


class TestPostSchedulerCRUD:
    def test_add_and_get(self, scheduler: PostScheduler) -> None:
        post = scheduler.add(_make_post())
        retrieved = scheduler.get(post.id)

        assert retrieved is not None
        assert retrieved.id == post.id
        assert retrieved.draft_id == "draft1"
        assert retrieved.platform == "instagram"

    def test_get_returns_none_for_missing(self, scheduler: PostScheduler) -> None:
        assert scheduler.get("nonexistent") is None

    def test_add_preserves_image_urls(self, scheduler: PostScheduler) -> None:
        post = scheduler.add(
            _make_post(image_urls=["https://a.com/1.jpg", "https://a.com/2.jpg"])
        )
        retrieved = scheduler.get(post.id)
        assert retrieved is not None
        assert retrieved.image_urls == ["https://a.com/1.jpg", "https://a.com/2.jpg"]

    def test_update_status_to_done(self, scheduler: PostScheduler) -> None:
        post = scheduler.add(_make_post())
        scheduler.update_status(post.id, "done")
        updated = scheduler.get(post.id)
        assert updated is not None
        assert updated.status == "done"
        assert updated.executed_at is not None

    def test_update_status_with_error(self, scheduler: PostScheduler) -> None:
        post = scheduler.add(_make_post())
        scheduler.update_status(post.id, "failed", error="API timeout")
        updated = scheduler.get(post.id)
        assert updated is not None
        assert updated.error == "API timeout"

    def test_cancel_pending_post(self, scheduler: PostScheduler) -> None:
        post = scheduler.add(_make_post())
        result = scheduler.cancel(post.id)
        assert result is True
        cancelled = scheduler.get(post.id)
        assert cancelled is not None
        assert cancelled.status == "failed"
        assert "Cancelled" in (cancelled.error or "")

    def test_cancel_non_pending_returns_false(self, scheduler: PostScheduler) -> None:
        post = scheduler.add(_make_post())
        scheduler.update_status(post.id, "done")
        result = scheduler.cancel(post.id)
        assert result is False


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


class TestPostSchedulerQueries:
    def test_list_pending_filters_status(self, scheduler: PostScheduler) -> None:
        p1 = scheduler.add(_make_post())
        p2 = scheduler.add(_make_post(draft_id="draft2"))
        scheduler.update_status(p2.id, "done")

        pending = scheduler.list_pending()
        assert len(pending) == 1
        assert pending[0].id == p1.id

    def test_list_due_returns_past_posts_only(self, scheduler: PostScheduler) -> None:
        scheduler.add(_make_post(scheduled_at=_future(60)))    # not due
        past_post = scheduler.add(_make_post(scheduled_at=_past(5)))  # due

        due = scheduler.list_due()
        assert len(due) == 1
        assert due[0].id == past_post.id

    def test_list_all_returns_everything(self, scheduler: PostScheduler) -> None:
        for i in range(3):
            scheduler.add(_make_post(draft_id=f"d{i}"))

        all_posts = scheduler.list_all()
        assert len(all_posts) == 3

    def test_stats_counts_by_status(self, scheduler: PostScheduler) -> None:
        p1 = scheduler.add(_make_post())
        p2 = scheduler.add(_make_post(draft_id="d2"))
        scheduler.update_status(p2.id, "done")

        stats = scheduler.stats()
        assert stats.get("pending", 0) == 1
        assert stats.get("done", 0) == 1
