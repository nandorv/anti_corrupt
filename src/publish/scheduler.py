"""
SQLite-backed post scheduler.

Posts can be queued for future publishing.  The ``run-due`` CLI command
(or a cron job) calls ``list_due()`` and dispatches each pending post
whose ``scheduled_at`` timestamp has passed.

Table: schedule
  id            TEXT PK
  draft_id      TEXT
  platform      TEXT  (instagram | twitter)
  scheduled_at  TEXT  (ISO 8601, UTC)
  status        TEXT  pending | running | done | failed
  created_at    TEXT
  executed_at   TEXT
  error         TEXT
  image_urls    TEXT  (JSON list — public image URLs for Instagram)
  caption       TEXT  (override caption; falls back to draft.formatted)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

import sqlite_utils
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

_VALID_PLATFORMS = {"instagram", "twitter"}
_VALID_STATUSES = {"pending", "running", "done", "failed"}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class ScheduledPost(BaseModel):
    """A single scheduled publishing task."""

    id: str = ""
    draft_id: str
    platform: str
    scheduled_at: dt.datetime
    status: str = "pending"
    created_at: dt.datetime = dt.datetime.now(dt.timezone.utc)
    executed_at: Optional[dt.datetime] = None
    error: Optional[str] = None
    image_urls: list[str] = []
    caption: str = ""

    def model_post_init(self, __context: object) -> None:  # noqa: D401
        if not self.id:
            self.id = str(uuid.uuid4())[:8]

    @field_validator("platform")
    @classmethod
    def _check_platform(cls, v: str) -> str:
        if v not in _VALID_PLATFORMS:
            raise ValueError(f"platform must be one of {sorted(_VALID_PLATFORMS)}, got {v!r}")
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)}, got {v!r}")
        return v

    @property
    def is_due(self) -> bool:
        """True if the post is pending and its scheduled time has passed."""
        now = dt.datetime.now(dt.timezone.utc)
        scheduled = (
            self.scheduled_at.replace(tzinfo=dt.timezone.utc)
            if self.scheduled_at.tzinfo is None
            else self.scheduled_at
        )
        return self.status == "pending" and scheduled <= now


# ---------------------------------------------------------------------------
# Scheduler / store
# ---------------------------------------------------------------------------


class PostScheduler:
    """
    Persistent schedule queue backed by a SQLite database.

    Usage::

        scheduler = PostScheduler(Path("output/schedule.db"))
        post = scheduler.add(ScheduledPost(
            draft_id="abc123",
            platform="instagram",
            scheduled_at=dt.datetime(2026, 3, 1, 10, 0, tzinfo=dt.timezone.utc),
            image_urls=["https://example.com/slide1.jpg"],
            caption="My caption",
        ))
        due = scheduler.list_due()
    """

    TABLE = "schedule"

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite_utils.Database(db_path)
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        if self.TABLE not in self._db.table_names():
            self._db[self.TABLE].create(
                {
                    "id": str,
                    "draft_id": str,
                    "platform": str,
                    "scheduled_at": str,
                    "status": str,
                    "created_at": str,
                    "executed_at": str,
                    "error": str,
                    "image_urls": str,
                    "caption": str,
                },
                pk="id",
            )
            self._db[self.TABLE].create_index(["status"])
            self._db[self.TABLE].create_index(["scheduled_at"])
            self._db[self.TABLE].create_index(["draft_id"])

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, post: ScheduledPost) -> ScheduledPost:
        """Persist a scheduled post and return it."""
        self._db[self.TABLE].insert(self._to_row(post), replace=True)
        logger.info(
            "Scheduled post %s (draft=%s) at %s on %s",
            post.id,
            post.draft_id,
            post.scheduled_at.isoformat(),
            post.platform,
        )
        return post

    def get(self, post_id: str) -> Optional[ScheduledPost]:
        """Return a ScheduledPost by id, or None if not found."""
        try:
            row = self._db[self.TABLE].get(post_id)
            return self._from_row(row)
        except sqlite_utils.db.NotFoundError:
            return None

    def update_status(
        self,
        post_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Update the status (and optionally record an error)."""
        update: dict = {"status": status}
        if status in ("done", "failed"):
            update["executed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        if error is not None:
            update["error"] = error
        self._db[self.TABLE].update(post_id, update)

    def cancel(self, post_id: str) -> bool:
        """Cancel a pending post. Returns True if it was pending and cancelled."""
        post = self.get(post_id)
        if post is None or post.status != "pending":
            return False
        self.update_status(post_id, "failed", error="Cancelled by user")
        logger.info("Cancelled scheduled post %s", post_id)
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_pending(self) -> list[ScheduledPost]:
        """Return all pending posts, sorted by scheduled_at ascending."""
        rows = list(
            self._db[self.TABLE].rows_where(
                "status = 'pending'",
                order_by="scheduled_at ASC",
            )
        )
        return [self._from_row(r) for r in rows]

    def list_due(self) -> list[ScheduledPost]:
        """Return pending posts whose scheduled_at is now or in the past."""
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        rows = list(
            self._db[self.TABLE].rows_where(
                "status = 'pending' AND scheduled_at <= ?",
                [now],
                order_by="scheduled_at ASC",
            )
        )
        return [self._from_row(r) for r in rows]

    def list_all(self, limit: int = 50) -> list[ScheduledPost]:
        """Return all posts (any status), most recently scheduled first."""
        rows = list(
            self._db[self.TABLE].rows_where(
                order_by="scheduled_at DESC",
                limit=limit,
            )
        )
        return [self._from_row(r) for r in rows]

    def stats(self) -> dict[str, int]:
        """Return count per status."""
        result: dict[str, int] = {}
        for row in self._db.execute(
            f"SELECT status, COUNT(*) FROM {self.TABLE} GROUP BY status"
        ).fetchall():
            result[row[0]] = row[1]
        return result

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_row(post: ScheduledPost) -> dict:
        return {
            "id": post.id,
            "draft_id": post.draft_id,
            "platform": post.platform,
            "scheduled_at": post.scheduled_at.isoformat(),
            "status": post.status,
            "created_at": post.created_at.isoformat(),
            "executed_at": post.executed_at.isoformat() if post.executed_at else None,
            "error": post.error,
            "image_urls": json.dumps(post.image_urls),
            "caption": post.caption,
        }

    @staticmethod
    def _from_row(row: dict) -> ScheduledPost:
        return ScheduledPost(
            id=row["id"],
            draft_id=row["draft_id"],
            platform=row["platform"],
            scheduled_at=dt.datetime.fromisoformat(row["scheduled_at"]),
            status=row["status"],
            created_at=dt.datetime.fromisoformat(row["created_at"]),
            executed_at=(
                dt.datetime.fromisoformat(row["executed_at"])
                if row["executed_at"]
                else None
            ),
            error=row["error"],
            image_urls=json.loads(row["image_urls"] or "[]"),
            caption=row["caption"] or "",
        )

    # ------------------------------------------------------------------
    # Context manager / cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "PostScheduler":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
