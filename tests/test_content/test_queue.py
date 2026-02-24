"""Tests for src/content/queue.py — ReviewQueue editorial workflow."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.content.models import ContentDraft, ContentStatus, ContentType
from src.content.queue import QueueStats, ReviewQueue
from src.content.storage import DraftStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> DraftStore:
    return DraftStore(tmp_path / "queue_test.db")


@pytest.fixture
def queue(store: DraftStore) -> ReviewQueue:
    return ReviewQueue(store=store)


def _make_draft(
    title: str = "Test Draft",
    body: str = "body content " * 20,
    content_type: ContentType = ContentType.NEWS_SUMMARY,
    status: ContentStatus = ContentStatus.DRAFT,
) -> ContentDraft:
    return ContentDraft(
        title=title,
        body=body,
        content_type=content_type,
        status=status,
    )


def _save(store: DraftStore, **kwargs) -> ContentDraft:
    d = _make_draft(**kwargs)
    store.save(d)
    return d


# ---------------------------------------------------------------------------
# list_pending / list_drafts / list_all
# ---------------------------------------------------------------------------


class TestQueueListing:
    def test_list_pending_returns_pending_only(
        self, queue: ReviewQueue, store: DraftStore
    ):
        d1 = _save(store, status=ContentStatus.PENDING_REVIEW)
        _save(store, status=ContentStatus.DRAFT)
        results = queue.list_pending()
        assert len(results) == 1
        assert results[0].id == d1.id

    def test_list_drafts_returns_draft_only(
        self, queue: ReviewQueue, store: DraftStore
    ):
        _save(store, status=ContentStatus.PENDING_REVIEW)
        d2 = _save(store, status=ContentStatus.DRAFT)
        results = queue.list_drafts()
        assert len(results) == 1
        assert results[0].id == d2.id

    def test_list_all_returns_all(self, queue: ReviewQueue, store: DraftStore):
        for i in range(4):
            _save(store, title=f"Draft {i}")
        results = queue.list_all()
        assert len(results) == 4

    def test_list_all_filtered_by_status(
        self, queue: ReviewQueue, store: DraftStore
    ):
        _save(store, status=ContentStatus.APPROVED)
        _save(store, status=ContentStatus.DRAFT)
        results = queue.list_all(status=ContentStatus.APPROVED)
        assert len(results) == 1

    def test_list_all_filtered_by_type(
        self, queue: ReviewQueue, store: DraftStore
    ):
        _save(store, content_type=ContentType.INSTITUTION_EXPLAINER)
        _save(store, content_type=ContentType.NEWS_SUMMARY)
        results = queue.list_all(content_type=ContentType.INSTITUTION_EXPLAINER)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# submit_for_review
# ---------------------------------------------------------------------------


class TestSubmitForReview:
    def test_submit_changes_status_to_pending(
        self, queue: ReviewQueue, store: DraftStore
    ):
        draft = _save(store, status=ContentStatus.DRAFT)
        result = queue.submit_for_review(draft.id)
        assert result.status == ContentStatus.PENDING_REVIEW

    def test_submit_persists_to_store(
        self, queue: ReviewQueue, store: DraftStore
    ):
        draft = _save(store, status=ContentStatus.DRAFT)
        queue.submit_for_review(draft.id)
        retrieved = store.get(draft.id)
        assert retrieved.status == ContentStatus.PENDING_REVIEW

    def test_submit_nonexistent_raises(self, queue: ReviewQueue):
        with pytest.raises(ValueError, match="not found"):
            queue.submit_for_review("nonexistent-id")


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------


class TestApprove:
    def test_approve_sets_status_approved(
        self, queue: ReviewQueue, store: DraftStore
    ):
        draft = _save(store, status=ContentStatus.PENDING_REVIEW)
        result = queue.approve(draft.id, reviewer="ed@test.com")
        assert result.status == ContentStatus.APPROVED

    def test_approve_stores_reviewer_note(
        self, queue: ReviewQueue, store: DraftStore
    ):
        draft = _save(store, status=ContentStatus.PENDING_REVIEW)
        queue.approve(draft.id, reviewer="ed@test.com", note="Looks great!")
        retrieved = store.get(draft.id)
        assert retrieved.review_notes[0].reviewer == "ed@test.com"
        assert retrieved.review_notes[0].note == "Looks great!"

    def test_approve_persists(self, queue: ReviewQueue, store: DraftStore):
        draft = _save(store, status=ContentStatus.PENDING_REVIEW)
        queue.approve(draft.id)
        retrieved = store.get(draft.id)
        assert retrieved.status == ContentStatus.APPROVED


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------


class TestReject:
    def test_reject_sets_status_rejected(
        self, queue: ReviewQueue, store: DraftStore
    ):
        draft = _save(store, status=ContentStatus.PENDING_REVIEW)
        result = queue.reject(draft.id, reviewer="ed@test.com", note="Needs revision")
        assert result.status == ContentStatus.REJECTED

    def test_reject_without_note_raises(
        self, queue: ReviewQueue, store: DraftStore
    ):
        draft = _save(store, status=ContentStatus.PENDING_REVIEW)
        with pytest.raises(ValueError, match="rejection note is required"):
            queue.reject(draft.id, reviewer="ed@test.com", note="")

    def test_reject_stores_note(self, queue: ReviewQueue, store: DraftStore):
        draft = _save(store, status=ContentStatus.PENDING_REVIEW)
        queue.reject(draft.id, note="Too speculative", reviewer="rev@test.com")
        retrieved = store.get(draft.id)
        assert retrieved.review_notes[0].note == "Too speculative"


# ---------------------------------------------------------------------------
# flag / unflag
# ---------------------------------------------------------------------------


class TestFlagUnflag:
    def test_flag_sets_flagged_true(self, queue: ReviewQueue, store: DraftStore):
        draft = _save(store)
        result = queue.flag(draft.id, reason="Verify statistics")
        assert result.flagged is True

    def test_flag_stores_reason(self, queue: ReviewQueue, store: DraftStore):
        draft = _save(store)
        queue.flag(draft.id, reason="Verify statistics")
        retrieved = store.get(draft.id)
        assert retrieved.flag_reason == "Verify statistics"

    def test_flag_does_not_change_status(
        self, queue: ReviewQueue, store: DraftStore
    ):
        draft = _save(store, status=ContentStatus.DRAFT)
        queue.flag(draft.id)
        retrieved = store.get(draft.id)
        assert retrieved.status == ContentStatus.DRAFT  # status unchanged

    def test_unflag_clears_flagged(self, queue: ReviewQueue, store: DraftStore):
        draft = _save(store)
        queue.flag(draft.id, reason="reason")
        queue.unflag(draft.id)
        retrieved = store.get(draft.id)
        assert retrieved.flagged is False
        assert retrieved.flag_reason is None

    def test_flag_appears_in_list_flagged(
        self, queue: ReviewQueue, store: DraftStore
    ):
        d1 = _save(store)
        d2 = _save(store)
        queue.flag(d1.id)
        flagged = store.list_flagged()
        assert len(flagged) == 1
        assert flagged[0].id == d1.id

    def test_unflag_removes_from_list_flagged(
        self, queue: ReviewQueue, store: DraftStore
    ):
        draft = _save(store)
        queue.flag(draft.id)
        queue.unflag(draft.id)
        assert store.list_flagged() == []


# ---------------------------------------------------------------------------
# update_body
# ---------------------------------------------------------------------------


class TestUpdateBody:
    def test_update_body_replaces_text(
        self, queue: ReviewQueue, store: DraftStore
    ):
        draft = _save(store)
        queue.update_body(draft.id, new_body="New corrected body " * 10)
        retrieved = store.get(draft.id)
        assert "New corrected body" in retrieved.body

    def test_update_body_adds_review_note(
        self, queue: ReviewQueue, store: DraftStore
    ):
        draft = _save(store)
        queue.update_body(draft.id, new_body="Updated " * 10, reviewer="ed@test.com")
        retrieved = store.get(draft.id)
        assert any(n.action == "edit" for n in retrieved.review_notes)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


class TestQueueStats:
    def test_stats_total(self, queue: ReviewQueue, store: DraftStore):
        _save(store)
        _save(store)
        stats = queue.stats()
        assert stats.total == 2

    def test_stats_pending_count(self, queue: ReviewQueue, store: DraftStore):
        _save(store, status=ContentStatus.PENDING_REVIEW)
        _save(store, status=ContentStatus.DRAFT)
        stats = queue.stats()
        assert stats.pending == 1
        assert stats.drafts == 1

    def test_stats_flagged_count(self, queue: ReviewQueue, store: DraftStore):
        d = _save(store)
        queue.flag(d.id)
        stats = queue.stats()
        assert stats.flagged == 1

    def test_stats_empty_store(self, queue: ReviewQueue):
        stats = queue.stats()
        assert stats.total == 0
        assert stats.pending == 0
        assert stats.flagged == 0

    def test_stats_is_queue_stats_instance(self, queue: ReviewQueue):
        assert isinstance(queue.stats(), QueueStats)
