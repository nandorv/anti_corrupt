"""
SQLite-backed persistent storage for ContentDraft objects.

Uses sqlite-utils for schema-free JSON column storage.
All drafts are stored in a single ``drafts`` table as JSON blobs,
with indexed columns for fast filtering (status, content_type, created_at).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import sqlite_utils

from src.content.models import ContentDraft, ContentStatus, ContentType

logger = logging.getLogger(__name__)

# DB schema version — bump when adding indexed columns
_SCHEMA_VERSION = 1


class DraftStore:
    """Persistent storage for ContentDraft objects backed by SQLite."""

    TABLE = "drafts"
    META_TABLE = "meta"

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite_utils.Database(db_path)
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        if self.TABLE not in self._db.table_names():
            self._db[self.TABLE].create(
                {
                    "id": str,
                    "content_type": str,
                    "status": str,
                    "title": str,
                    "tags": str,           # JSON list
                    "created_at": str,
                    "updated_at": str,
                    "flagged": int,
                    "data": str,           # full JSON blob
                },
                pk="id",
                not_null={"id", "content_type", "status"},
            )
            # Indexes for common query patterns
            self._db[self.TABLE].create_index(["status"])
            self._db[self.TABLE].create_index(["content_type"])
            self._db[self.TABLE].create_index(["created_at"])
            self._db[self.TABLE].create_index(["flagged"])
            logger.debug("Created drafts table")

        # Metadata / versioning
        if self.META_TABLE not in self._db.table_names():
            self._db[self.META_TABLE].insert(
                {"key": "schema_version", "value": str(_SCHEMA_VERSION)}
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save(self, draft: ContentDraft) -> None:
        """Insert or replace a draft."""
        record = {
            "id": draft.id,
            "content_type": draft.content_type.value,
            "status": draft.status.value,
            "title": draft.title,
            "tags": json.dumps(draft.tags, ensure_ascii=False),
            "created_at": draft.created_at.isoformat(),
            "updated_at": draft.updated_at.isoformat(),
            "flagged": int(draft.flagged),
            "data": json.dumps(draft.to_dict(), ensure_ascii=False),
        }
        self._db[self.TABLE].insert(record, replace=True)

    def get(self, draft_id: str) -> Optional[ContentDraft]:
        """Return a ContentDraft by id, or None if not found."""
        try:
            row = self._db[self.TABLE].get(draft_id)
            return ContentDraft.from_dict(json.loads(row["data"]))
        except sqlite_utils.db.NotFoundError:
            return None

    def delete(self, draft_id: str) -> bool:
        """Delete a draft. Returns True if it existed."""
        if self.get(draft_id) is None:
            return False
        self._db[self.TABLE].delete(draft_id)
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_by_status(
        self,
        status: ContentStatus,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ContentDraft]:
        rows = list(
            self._db[self.TABLE].rows_where(
                "status = ?",
                [status.value],
                order_by="created_at DESC",
                limit=limit,
                offset=offset,
            )
        )
        return [ContentDraft.from_dict(json.loads(r["data"])) for r in rows]

    def list_by_type(
        self,
        content_type: ContentType,
        limit: int = 50,
    ) -> list[ContentDraft]:
        rows = list(
            self._db[self.TABLE].rows_where(
                "content_type = ?",
                [content_type.value],
                order_by="created_at DESC",
                limit=limit,
            )
        )
        return [ContentDraft.from_dict(json.loads(r["data"])) for r in rows]

    def list_flagged(self) -> list[ContentDraft]:
        rows = list(
            self._db[self.TABLE].rows_where(
                "flagged = 1", order_by="created_at DESC"
            )
        )
        return [ContentDraft.from_dict(json.loads(r["data"])) for r in rows]

    def list_all(self, limit: int = 100, offset: int = 0) -> list[ContentDraft]:
        rows = list(
            self._db[self.TABLE].rows_where(
                order_by="created_at DESC",
                limit=limit,
                offset=offset,
            )
        )
        return [ContentDraft.from_dict(json.loads(r["data"])) for r in rows]

    def count(self, status: Optional[ContentStatus] = None) -> int:
        if status:
            return self._db.execute(
                f"SELECT COUNT(*) FROM {self.TABLE} WHERE status = ?", [status.value]
            ).fetchone()[0]
        return self._db.execute(f"SELECT COUNT(*) FROM {self.TABLE}").fetchone()[0]

    def stats(self) -> dict:
        """Return count per status."""
        result: dict = {}
        for row in self._db.execute(
            f"SELECT status, COUNT(*) as n FROM {self.TABLE} GROUP BY status"
        ).fetchall():
            result[row[0]] = row[1]
        return result

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "DraftStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store: Optional[DraftStore] = None


def get_store() -> DraftStore:
    """Return the application-wide DraftStore (lazy init)."""
    global _store
    if _store is None:
        from config.settings import settings  # noqa: PLC0415

        db_path = settings.output_dir / "drafts.db"
        _store = DraftStore(db_path)
    return _store
