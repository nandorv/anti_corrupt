"""
Editorial review queue.

Provides a high-level API used by the CLI review commands:
  - list pending drafts
  - approve / reject with notes
  - flag for human attention
  - queue statistics
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.content.models import ContentDraft, ContentStatus, ContentType
from src.content.storage import DraftStore, get_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Queue statistics
# ---------------------------------------------------------------------------


@dataclass
class QueueStats:
    total: int
    by_status: dict[str, int]
    flagged: int

    @property
    def pending(self) -> int:
        return self.by_status.get(ContentStatus.PENDING_REVIEW.value, 0)

    @property
    def drafts(self) -> int:
        return self.by_status.get(ContentStatus.DRAFT.value, 0)

    @property
    def approved(self) -> int:
        return self.by_status.get(ContentStatus.APPROVED.value, 0)

    @property
    def published(self) -> int:
        return self.by_status.get(ContentStatus.PUBLISHED.value, 0)


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------


class ReviewQueue:
    """High-level review workflow built on top of DraftStore."""

    def __init__(self, store: Optional[DraftStore] = None) -> None:
        self.store = store or get_store()

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_pending(self, limit: int = 50) -> list[ContentDraft]:
        """All drafts in PENDING_REVIEW state, oldest first."""
        drafts = self.store.list_by_status(ContentStatus.PENDING_REVIEW, limit=limit)
        return sorted(drafts, key=lambda d: d.created_at)

    def list_drafts(self, limit: int = 50) -> list[ContentDraft]:
        """All drafts in DRAFT state."""
        return self.store.list_by_status(ContentStatus.DRAFT, limit=limit)

    def list_all(
        self,
        status: Optional[ContentStatus] = None,
        content_type: Optional[ContentType] = None,
        limit: int = 100,
    ) -> list[ContentDraft]:
        if status:
            return self.store.list_by_status(status, limit=limit)
        if content_type:
            return self.store.list_by_type(content_type, limit=limit)
        return self.store.list_all(limit=limit)

    def get(self, draft_id: str) -> Optional[ContentDraft]:
        return self.store.get(draft_id)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def submit_for_review(self, draft_id: str) -> ContentDraft:
        """Move a DRAFT to PENDING_REVIEW."""
        draft = self._require(draft_id)
        draft.transition_to(ContentStatus.PENDING_REVIEW)
        self.store.save(draft)
        logger.info("Submitted for review: %s", draft_id)
        return draft

    def approve(
        self, draft_id: str, reviewer: str = "editor", note: str = ""
    ) -> ContentDraft:
        """Approve a PENDING_REVIEW draft."""
        draft = self._require(draft_id)
        draft.approve(reviewer=reviewer, note=note)
        self.store.save(draft)
        logger.info("Approved: %s by %s", draft_id, reviewer)
        return draft

    def reject(
        self, draft_id: str, reviewer: str = "editor", note: str = ""
    ) -> ContentDraft:
        """Reject a PENDING_REVIEW draft with a note."""
        if not note:
            raise ValueError("A rejection note is required.")
        draft = self._require(draft_id)
        draft.reject(reviewer=reviewer, note=note)
        self.store.save(draft)
        logger.info("Rejected: %s by %s — %s", draft_id, reviewer, note)
        return draft

    def flag(
        self, draft_id: str, reason: str = "", reviewer: str = "editor"
    ) -> ContentDraft:
        """Flag a draft for special attention without changing status."""
        draft = self._require(draft_id)
        draft.flagged = True
        draft.flag_reason = reason
        draft.add_review_note(reviewer, f"[FLAGGED] {reason}", action="flag")
        self.store.save(draft)
        return draft

    def unflag(self, draft_id: str) -> ContentDraft:
        draft = self._require(draft_id)
        draft.flagged = False
        draft.flag_reason = None
        draft.touch()
        self.store.save(draft)
        return draft

    def update_body(
        self, draft_id: str, new_body: str, reviewer: str = "editor"
    ) -> ContentDraft:
        """Replace the body text and add an edit note."""
        draft = self._require(draft_id)
        draft.body = new_body
        draft.add_review_note(reviewer, "Conteúdo editado manualmente.", action="edit")
        self.store.save(draft)
        return draft

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> QueueStats:
        total = self.store.count()
        by_status = self.store.stats()
        flagged = len(self.store.list_flagged())
        return QueueStats(total=total, by_status=by_status, flagged=flagged)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require(self, draft_id: str) -> ContentDraft:
        draft = self.store.get(draft_id)
        if not draft:
            raise ValueError(f"Draft not found: {draft_id!r}")
        return draft
