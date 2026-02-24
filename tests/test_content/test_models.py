"""Tests for src/content/models.py — ContentDraft state machine."""

from __future__ import annotations

import pytest

from src.content.models import (
    ContentDraft,
    ContentStatus,
    ContentType,
    Platform,
    ReviewNote,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_draft(
    title: str = "Explainer: O que é o STF?",
    body: str = "O STF é o Supremo Tribunal Federal. " * 20,
    content_type: ContentType = ContentType.INSTITUTION_EXPLAINER,
    status: ContentStatus = ContentStatus.DRAFT,
) -> ContentDraft:
    return ContentDraft(
        title=title,
        body=body,
        content_type=content_type,
        status=status,
    )


# ---------------------------------------------------------------------------
# ContentDraft basic properties
# ---------------------------------------------------------------------------


class TestContentDraftProperties:
    def test_default_status_is_draft(self):
        draft = _make_draft()
        assert draft.status == ContentStatus.DRAFT

    def test_id_auto_generated(self):
        draft = _make_draft()
        assert draft.id is not None
        assert len(draft.id) == 8  # uuid4()[:8]

    def test_two_drafts_have_different_ids(self):
        d1 = _make_draft()
        d2 = _make_draft()
        assert d1.id != d2.id

    def test_word_count(self):
        body = "word " * 50
        draft = _make_draft(body=body)
        assert draft.word_count == 50

    def test_content_hash_is_12_chars(self):
        draft = _make_draft()
        assert len(draft.content_hash) == 12

    def test_content_hash_differs_for_different_body(self):
        d1 = _make_draft(body="alpha beta gamma " * 10)
        d2 = _make_draft(body="delta epsilon zeta " * 10)
        assert d1.content_hash != d2.content_hash

    def test_content_hash_same_for_same_body(self):
        body = "consistent content " * 10
        d1 = _make_draft(body=body)
        d2 = _make_draft(body=body)
        assert d1.content_hash == d2.content_hash

    def test_default_language_is_pt_br(self):
        draft = _make_draft()
        assert draft.language == "pt-BR"

    def test_flagged_default_false(self):
        draft = _make_draft()
        assert draft.flagged is False


# ---------------------------------------------------------------------------
# State machine: transition_to()
# ---------------------------------------------------------------------------


class TestStateMachineTransitions:
    def test_raw_to_draft_allowed(self):
        draft = _make_draft(status=ContentStatus.RAW)
        draft.transition_to(ContentStatus.DRAFT)
        assert draft.status == ContentStatus.DRAFT

    def test_draft_to_pending_review_allowed(self):
        draft = _make_draft(status=ContentStatus.DRAFT)
        draft.transition_to(ContentStatus.PENDING_REVIEW)
        assert draft.status == ContentStatus.PENDING_REVIEW

    def test_draft_to_archived_allowed(self):
        draft = _make_draft(status=ContentStatus.DRAFT)
        draft.transition_to(ContentStatus.ARCHIVED)
        assert draft.status == ContentStatus.ARCHIVED

    def test_pending_review_to_approved_allowed(self):
        draft = _make_draft(status=ContentStatus.PENDING_REVIEW)
        draft.transition_to(ContentStatus.APPROVED)
        assert draft.status == ContentStatus.APPROVED

    def test_pending_review_to_rejected_allowed(self):
        draft = _make_draft(status=ContentStatus.PENDING_REVIEW)
        draft.transition_to(ContentStatus.REJECTED)
        assert draft.status == ContentStatus.REJECTED

    def test_approved_to_published_allowed(self):
        draft = _make_draft(status=ContentStatus.APPROVED)
        draft.transition_to(ContentStatus.PUBLISHED)
        assert draft.status == ContentStatus.PUBLISHED

    def test_rejected_to_draft_allowed(self):
        draft = _make_draft(status=ContentStatus.REJECTED)
        draft.transition_to(ContentStatus.DRAFT)
        assert draft.status == ContentStatus.DRAFT

    def test_published_to_archived_allowed(self):
        draft = _make_draft(status=ContentStatus.PUBLISHED)
        draft.transition_to(ContentStatus.ARCHIVED)
        assert draft.status == ContentStatus.ARCHIVED

    def test_invalid_transition_raises_value_error(self):
        draft = _make_draft(status=ContentStatus.DRAFT)
        with pytest.raises(ValueError, match="Invalid transition"):
            draft.transition_to(ContentStatus.PUBLISHED)

    def test_raw_to_published_raises(self):
        draft = _make_draft(status=ContentStatus.RAW)
        with pytest.raises(ValueError):
            draft.transition_to(ContentStatus.PUBLISHED)

    def test_archived_to_anything_raises(self):
        draft = _make_draft(status=ContentStatus.ARCHIVED)
        with pytest.raises(ValueError):
            draft.transition_to(ContentStatus.DRAFT)

    def test_transition_updates_updated_at(self):
        import datetime as dt

        draft = _make_draft(status=ContentStatus.DRAFT)
        before = draft.updated_at
        draft.transition_to(ContentStatus.PENDING_REVIEW)
        assert draft.updated_at >= before


# ---------------------------------------------------------------------------
# approve() / reject()
# ---------------------------------------------------------------------------


class TestApproveReject:
    def test_approve_sets_status_approved(self):
        draft = _make_draft(status=ContentStatus.PENDING_REVIEW)
        draft.approve(reviewer="editor@test.com")
        assert draft.status == ContentStatus.APPROVED

    def test_approve_adds_review_note(self):
        draft = _make_draft(status=ContentStatus.PENDING_REVIEW)
        draft.approve(reviewer="editor@test.com", note="Looks great")
        assert len(draft.review_notes) == 1
        assert draft.review_notes[0].reviewer == "editor@test.com"
        assert draft.review_notes[0].action == "approve"

    def test_approve_from_wrong_state_raises(self):
        draft = _make_draft(status=ContentStatus.DRAFT)
        with pytest.raises(ValueError):
            draft.approve(reviewer="editor@test.com")

    def test_reject_sets_status_rejected(self):
        draft = _make_draft(status=ContentStatus.PENDING_REVIEW)
        draft.reject(reviewer="editor@test.com", note="Needs more sources")
        assert draft.status == ContentStatus.REJECTED

    def test_reject_stores_note(self):
        draft = _make_draft(status=ContentStatus.PENDING_REVIEW)
        draft.reject(reviewer="ed@test.com", note="Too speculative")
        assert draft.review_notes[0].note == "Too speculative"
        assert draft.review_notes[0].action == "reject"


# ---------------------------------------------------------------------------
# mark_published()
# ---------------------------------------------------------------------------


class TestMarkPublished:
    def test_mark_published_sets_status(self):
        draft = _make_draft(status=ContentStatus.APPROVED)
        draft.mark_published(platform=Platform.INSTAGRAM)
        assert draft.status == ContentStatus.PUBLISHED

    def test_mark_published_adds_publish_record(self):
        draft = _make_draft(status=ContentStatus.APPROVED)
        draft.mark_published(platform=Platform.X, url="https://x.com/post/1")
        assert len(draft.publish_records) == 1
        assert draft.publish_records[0].platform == Platform.X

    def test_mark_published_sets_published_at(self):
        draft = _make_draft(status=ContentStatus.APPROVED)
        draft.mark_published(platform=Platform.NEWSLETTER)
        assert draft.published_at is not None

    def test_mark_published_from_wrong_state_raises(self):
        draft = _make_draft(status=ContentStatus.DRAFT)
        with pytest.raises(ValueError):
            draft.mark_published(platform=Platform.INSTAGRAM)


# ---------------------------------------------------------------------------
# add_review_note()
# ---------------------------------------------------------------------------


class TestAddReviewNote:
    def test_add_note_stored(self):
        draft = _make_draft()
        draft.add_review_note(reviewer="rev@test.com", note="Minor fix needed")
        assert len(draft.review_notes) == 1
        note = draft.review_notes[0]
        assert note.reviewer == "rev@test.com"
        assert note.note == "Minor fix needed"

    def test_multiple_notes(self):
        draft = _make_draft()
        draft.add_review_note(reviewer="a", note="First note")
        draft.add_review_note(reviewer="b", note="Second note")
        assert len(draft.review_notes) == 2

    def test_reviewed_at_set(self):
        draft = _make_draft()
        assert draft.reviewed_at is None
        draft.add_review_note(reviewer="rev@test.com", note="Good")
        assert draft.reviewed_at is not None


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_and_from_dict_roundtrip(self):
        draft = _make_draft()
        draft.tags = ["stf", "judiciário"]
        d = draft.to_dict()
        restored = ContentDraft.from_dict(d)
        assert restored.id == draft.id
        assert restored.title == draft.title
        assert restored.status == draft.status
        assert restored.tags == draft.tags

    def test_status_coerced_from_string(self):
        draft = ContentDraft(
            title="Test",
            body="body " * 10,
            content_type=ContentType.NEWS_SUMMARY,
            status="pending_review",  # type: ignore[arg-type]
        )
        assert draft.status == ContentStatus.PENDING_REVIEW
