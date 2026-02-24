"""
Tests for src/publish/analytics.py
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from src.publish.analytics import AnalyticsStore, MetricRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> AnalyticsStore:
    return AnalyticsStore(tmp_path / "analytics.db")


# ---------------------------------------------------------------------------
# MetricRecord model
# ---------------------------------------------------------------------------


class TestMetricRecord:
    def test_id_computed_from_fields(self) -> None:
        rec = MetricRecord(
            post_id="POST1",
            platform="instagram",
            draft_id="DRAFT1",
            metric_name="impressions",
            metric_value=1000.0,
        )
        assert rec.id == "instagram:POST1:impressions"

    def test_default_fetched_at_is_recent(self) -> None:
        rec = MetricRecord(
            post_id="P",
            platform="twitter",
            draft_id="D",
            metric_name="likes",
            metric_value=5.0,
        )
        delta = dt.datetime.now(dt.timezone.utc) - rec.fetched_at.replace(
            tzinfo=dt.timezone.utc
        )
        assert abs(delta.total_seconds()) < 5


# ---------------------------------------------------------------------------
# store / store_batch
# ---------------------------------------------------------------------------


class TestAnalyticsStoreWrite:
    def test_store_single_record(self, store: AnalyticsStore) -> None:
        rec = MetricRecord(
            post_id="P1",
            platform="instagram",
            draft_id="D1",
            metric_name="reach",
            metric_value=500.0,
        )
        store.store(rec)

        result = store.get_post_metrics("P1", "instagram")
        assert result["reach"] == 500.0

    def test_store_batch_writes_all_metrics(self, store: AnalyticsStore) -> None:
        store.store_batch(
            post_id="P2",
            platform="instagram",
            draft_id="D2",
            metrics={"impressions": 1200, "reach": 900, "likes": 60, "comments": 8},
        )

        result = store.get_post_metrics("P2", "instagram")
        assert result["impressions"] == 1200
        assert result["reach"] == 900
        assert result["likes"] == 60
        assert result["comments"] == 8

    def test_store_updates_existing_record(self, store: AnalyticsStore) -> None:
        store.store_batch("P3", "twitter", "D3", {"like_count": 10})
        store.store_batch("P3", "twitter", "D3", {"like_count": 25})  # update

        result = store.get_post_metrics("P3", "twitter")
        assert result["like_count"] == 25


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


class TestAnalyticsStoreRead:
    def test_get_post_metrics_returns_empty_for_unknown(self, store: AnalyticsStore) -> None:
        result = store.get_post_metrics("NOPE", "instagram")
        assert result == {}

    def test_get_draft_metrics_returns_all_platforms(self, store: AnalyticsStore) -> None:
        store.store_batch("IG_POST", "instagram", "DRAFT1", {"impressions": 100})
        store.store_batch("TW_POST", "twitter", "DRAFT1", {"like_count": 5})

        rows = store.get_draft_metrics("DRAFT1")
        platforms = {r["platform"] for r in rows}
        assert "instagram" in platforms
        assert "twitter" in platforms

    def test_top_posts_returns_sorted_by_metric(self, store: AnalyticsStore) -> None:
        store.store_batch("POST_A", "instagram", "D_A", {"impressions": 500})
        store.store_batch("POST_B", "instagram", "D_B", {"impressions": 1500})
        store.store_batch("POST_C", "instagram", "D_C", {"impressions": 300})

        top = store.top_posts("instagram", metric="impressions", limit=2)

        assert len(top) == 2
        assert top[0]["post_id"] == "POST_B"  # highest
        assert top[1]["post_id"] == "POST_A"  # second highest

    def test_summary_counts_correctly(self, store: AnalyticsStore) -> None:
        store.store_batch("IG1", "instagram", "D1", {"impressions": 100, "reach": 80})
        store.store_batch("IG2", "instagram", "D2", {"impressions": 200})

        summary = store.summary("instagram")
        assert summary["total_metric_records"] == 3
        assert summary["distinct_posts"] == 2
        assert summary["platform"] == "instagram"
