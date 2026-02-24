"""
Post performance analytics store.

Stores metrics fetched from Instagram and X/Twitter so we can track
performance over time and compare content types.

Metrics table:
  id            TEXT PK  (platform:post_id:metric_name)
  post_id       TEXT
  platform      TEXT  (instagram | twitter)
  draft_id      TEXT
  metric_name   TEXT
  metric_value  REAL
  fetched_at    TEXT  (ISO 8601)

Example metrics:
  Instagram: impressions, reach, likes, comments, saved, shares
  Twitter:   like_count, retweet_count, reply_count, quote_count, impression_count
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Optional

import sqlite_utils
from pydantic import BaseModel, computed_field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class MetricRecord(BaseModel):
    """A single metric snapshot for a published post."""

    post_id: str
    platform: str
    draft_id: str
    metric_name: str
    metric_value: float
    fetched_at: dt.datetime = dt.datetime.now(dt.timezone.utc)

    @computed_field  # type: ignore[misc]
    @property
    def id(self) -> str:
        return f"{self.platform}:{self.post_id}:{self.metric_name}"


# ---------------------------------------------------------------------------
# Analytics store
# ---------------------------------------------------------------------------


class AnalyticsStore:
    """
    Persistent analytics storage backed by SQLite.

    Usage::

        store = AnalyticsStore(Path("output/analytics.db"))
        store.store_batch(
            post_id="123456789",
            platform="instagram",
            draft_id="abc123",
            metrics={"impressions": 1500, "reach": 1100, "likes": 87},
        )
        metrics = store.get_post_metrics("123456789", "instagram")
        top = store.top_posts("instagram", metric="impressions")
    """

    TABLE = "metrics"

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
                    "post_id": str,
                    "platform": str,
                    "draft_id": str,
                    "metric_name": str,
                    "metric_value": float,
                    "fetched_at": str,
                },
                pk="id",
            )
            self._db[self.TABLE].create_index(["post_id"])
            self._db[self.TABLE].create_index(["draft_id"])
            self._db[self.TABLE].create_index(["platform"])
            self._db[self.TABLE].create_index(["metric_name"])

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store(self, record: MetricRecord) -> None:
        """Upsert a single metric record."""
        self._db[self.TABLE].insert(
            {
                "id": record.id,
                "post_id": record.post_id,
                "platform": record.platform,
                "draft_id": record.draft_id,
                "metric_name": record.metric_name,
                "metric_value": record.metric_value,
                "fetched_at": record.fetched_at.isoformat(),
            },
            replace=True,
        )

    def store_batch(
        self,
        post_id: str,
        platform: str,
        draft_id: str,
        metrics: dict[str, float],
    ) -> None:
        """Store multiple metrics for a single post snapshot."""
        now = dt.datetime.now(dt.timezone.utc)
        for name, value in metrics.items():
            self.store(
                MetricRecord(
                    post_id=post_id,
                    platform=platform,
                    draft_id=draft_id,
                    metric_name=name,
                    metric_value=float(value),
                    fetched_at=now,
                )
            )
        logger.info(
            "Stored %d metrics for %s/%s (draft=%s)",
            len(metrics),
            platform,
            post_id,
            draft_id,
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_post_metrics(self, post_id: str, platform: str) -> dict[str, float]:
        """Return all metrics for a specific post as {name: value}."""
        rows = list(
            self._db[self.TABLE].rows_where(
                "post_id = ? AND platform = ?",
                [post_id, platform],
            )
        )
        return {r["metric_name"]: r["metric_value"] for r in rows}

    def get_draft_metrics(self, draft_id: str) -> list[dict]:
        """Return all metric rows associated with a draft (all platforms)."""
        rows = list(
            self._db[self.TABLE].rows_where(
                "draft_id = ?",
                [draft_id],
                order_by="platform, metric_name",
            )
        )
        return list(rows)

    def top_posts(
        self,
        platform: str,
        metric: str = "impressions",
        limit: int = 10,
    ) -> list[dict]:
        """Return top N posts by a given metric on a platform."""
        rows = self._db.execute(
            f"""
            SELECT post_id, draft_id, metric_value, fetched_at
            FROM {self.TABLE}
            WHERE platform = ? AND metric_name = ?
            ORDER BY metric_value DESC
            LIMIT ?
            """,
            [platform, metric, limit],
        ).fetchall()
        return [
            {
                "post_id": r[0],
                "draft_id": r[1],
                metric: r[2],
                "fetched_at": r[3],
            }
            for r in rows
        ]

    def summary(self, platform: Optional[str] = None) -> dict:
        """Return aggregate stats: total posts, total metrics stored."""
        where = "WHERE platform = ?" if platform else ""
        params = [platform] if platform else []

        total_metrics = self._db.execute(
            f"SELECT COUNT(*) FROM {self.TABLE} {where}", params
        ).fetchone()[0]

        posts = self._db.execute(
            f"SELECT COUNT(DISTINCT post_id) FROM {self.TABLE} {where}", params
        ).fetchone()[0]

        return {
            "platform": platform or "all",
            "total_metric_records": total_metrics,
            "distinct_posts": posts,
        }

    # ------------------------------------------------------------------
    # Context manager / cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "AnalyticsStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
