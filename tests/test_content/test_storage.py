"""Tests for src/content/storage.py — SQLite DraftStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.content.models import ContentDraft, ContentStatus, ContentType
from src.content.storage import DraftStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> DraftStore:
    """Create a fresh in-memory DraftStore for each test."""
    return DraftStore(tmp_path / "test_drafts.db")


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


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestDraftStoreCRUD:
    def test_save_and_get_roundtrip(self, store: DraftStore):
        draft = _make_draft(title="Roundtrip Test")
        store.save(draft)
        retrieved = store.get(draft.id)
        assert retrieved is not None
        assert retrieved.id == draft.id
        assert retrieved.title == "Roundtrip Test"

    def test_get_nonexistent_returns_none(self, store: DraftStore):
        result = store.get("nonexistent-id")
        assert result is None

    def test_save_updates_existing(self, store: DraftStore):
        draft = _make_draft(title="Original Title")
        store.save(draft)

        draft.title = "Updated Title"
        store.save(draft)

        retrieved = store.get(draft.id)
        assert retrieved is not None
        assert retrieved.title == "Updated Title"

    def test_delete_existing_returns_true(self, store: DraftStore):
        draft = _make_draft()
        store.save(draft)
        result = store.delete(draft.id)
        assert result is True

    def test_delete_removes_from_store(self, store: DraftStore):
        draft = _make_draft()
        store.save(draft)
        store.delete(draft.id)
        assert store.get(draft.id) is None

    def test_delete_nonexistent_returns_false(self, store: DraftStore):
        result = store.delete("nonexistent-id")
        assert result is False

    def test_save_preserves_status(self, store: DraftStore):
        draft = _make_draft(status=ContentStatus.PENDING_REVIEW)
        store.save(draft)
        retrieved = store.get(draft.id)
        assert retrieved.status == ContentStatus.PENDING_REVIEW

    def test_save_preserves_tags(self, store: DraftStore):
        draft = _make_draft()
        draft.tags = ["stf", "judiciário", "transparência"]
        store.save(draft)
        retrieved = store.get(draft.id)
        assert retrieved.tags == ["stf", "judiciário", "transparência"]

    def test_save_preserves_review_notes(self, store: DraftStore):
        draft = _make_draft(status=ContentStatus.PENDING_REVIEW)
        draft.approve(reviewer="ed@test.com", note="Great work")
        store.save(draft)
        retrieved = store.get(draft.id)
        assert len(retrieved.review_notes) == 1
        assert retrieved.review_notes[0].reviewer == "ed@test.com"


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


class TestDraftStoreQueries:
    def test_list_by_status_returns_matching(self, store: DraftStore):
        d1 = _make_draft(status=ContentStatus.DRAFT)
        d2 = _make_draft(status=ContentStatus.DRAFT)
        d3 = _make_draft(status=ContentStatus.APPROVED)
        for d in [d1, d2, d3]:
            store.save(d)

        results = store.list_by_status(ContentStatus.DRAFT)
        ids = {r.id for r in results}
        assert d1.id in ids
        assert d2.id in ids
        assert d3.id not in ids

    def test_list_by_status_empty_returns_empty(self, store: DraftStore):
        results = store.list_by_status(ContentStatus.PUBLISHED)
        assert results == []

    def test_list_by_type_returns_matching(self, store: DraftStore):
        d1 = _make_draft(content_type=ContentType.INSTITUTION_EXPLAINER)
        d2 = _make_draft(content_type=ContentType.NEWS_SUMMARY)
        store.save(d1)
        store.save(d2)

        results = store.list_by_type(ContentType.INSTITUTION_EXPLAINER)
        assert len(results) == 1
        assert results[0].id == d1.id

    def test_list_flagged_returns_flagged_only(self, store: DraftStore):
        d1 = _make_draft()
        d1.flagged = True
        d2 = _make_draft()
        d2.flagged = False
        store.save(d1)
        store.save(d2)

        flagged = store.list_flagged()
        assert len(flagged) == 1
        assert flagged[0].id == d1.id

    def test_list_all_returns_all(self, store: DraftStore):
        for i in range(5):
            store.save(_make_draft(title=f"Draft {i}"))
        results = store.list_all()
        assert len(results) == 5

    def test_list_all_respects_limit(self, store: DraftStore):
        for i in range(10):
            store.save(_make_draft(title=f"Draft {i}"))
        results = store.list_all(limit=3)
        assert len(results) == 3

    def test_count_total(self, store: DraftStore):
        store.save(_make_draft())
        store.save(_make_draft())
        assert store.count() == 2

    def test_count_by_status(self, store: DraftStore):
        store.save(_make_draft(status=ContentStatus.DRAFT))
        store.save(_make_draft(status=ContentStatus.DRAFT))
        store.save(_make_draft(status=ContentStatus.APPROVED))
        assert store.count(ContentStatus.DRAFT) == 2
        assert store.count(ContentStatus.APPROVED) == 1

    def test_stats_returns_dict(self, store: DraftStore):
        store.save(_make_draft(status=ContentStatus.DRAFT))
        store.save(_make_draft(status=ContentStatus.APPROVED))
        stats = store.stats()
        assert isinstance(stats, dict)
        assert stats.get("draft") == 1
        assert stats.get("approved") == 1

    def test_stats_empty_store(self, store: DraftStore):
        stats = store.stats()
        assert stats == {}


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestDraftStoreContextManager:
    def test_context_manager(self, tmp_path: Path):
        with DraftStore(tmp_path / "ctx.db") as s:
            draft = _make_draft()
            s.save(draft)
            assert s.get(draft.id) is not None
        # No exception — clean close
