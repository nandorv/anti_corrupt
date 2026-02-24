"""
Tests for the API cache module (src/sources/cache.py).
"""

import datetime as dt
import gzip
import json
from pathlib import Path

import pytest

from src.sources.cache import APICache, CacheEntry, DEFAULT_TTL


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cache(tmp_path):
    """Return a fresh APICache backed by a temp SQLite file."""
    return APICache(db_path=tmp_path / "test_cache.db")


SAMPLE_DATA = {"id": 123, "nome": "Test Deputy", "partido": "PT"}


# ---------------------------------------------------------------------------
# CacheEntry tests
# ---------------------------------------------------------------------------

class TestCacheEntry:
    def test_fresh_entry(self):
        entry = CacheEntry(
            key="test/key",
            source="camara_deputados",
            data=SAMPLE_DATA,
            fetched_at=dt.datetime.now(dt.timezone.utc),
        )
        assert entry.is_fresh(ttl_seconds=3600) is True

    def test_stale_entry(self):
        old_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=25)
        entry = CacheEntry(
            key="test/key",
            source="camara_deputados",
            data=SAMPLE_DATA,
            fetched_at=old_time,
        )
        assert entry.is_fresh(ttl_seconds=3600) is False

    def test_age_seconds(self):
        past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=300)
        entry = CacheEntry(key="k", source="s", data={}, fetched_at=past)
        assert 295 < entry.age_seconds < 310

    def test_to_dict_keys(self):
        entry = CacheEntry(key="k", source="s", data={"x": 1}, fetched_at=dt.datetime.now(dt.timezone.utc))
        d = entry.to_dict()
        assert set(d.keys()) == {"key", "source", "data_json", "fetched_at", "schema_version"}

    def test_from_row_roundtrip(self):
        entry = CacheEntry(key="k", source="s", data={"x": 1}, fetched_at=dt.datetime.now(dt.timezone.utc))
        restored = CacheEntry.from_row(entry.to_dict())
        assert restored.key == "k"
        assert restored.data == {"x": 1}
        assert restored.source == "s"

    def test_naive_datetime_still_fresh(self):
        """Naive datetimes (no tzinfo) should be treated as UTC."""
        naive = dt.datetime.utcnow()
        entry = CacheEntry(key="k", source="s", data={}, fetched_at=naive)
        assert entry.is_fresh(ttl_seconds=3600) is True


# ---------------------------------------------------------------------------
# APICache CRUD tests
# ---------------------------------------------------------------------------

class TestAPICacheCRUD:
    def test_set_and_get(self, cache):
        cache.set("camara/dep/1", data=SAMPLE_DATA, source="camara_deputados")
        entry = cache.get("camara/dep/1")
        assert entry is not None
        assert entry.data == SAMPLE_DATA
        assert entry.source == "camara_deputados"

    def test_get_missing_key(self, cache):
        assert cache.get("nonexistent/key") is None

    def test_overwrite_entry(self, cache):
        cache.set("k", data={"v": 1}, source="s")
        cache.set("k", data={"v": 2}, source="s")
        entry = cache.get("k")
        assert entry.data == {"v": 2}

    def test_delete(self, cache):
        cache.set("k", data={}, source="s")
        cache.delete("k")
        assert cache.get("k") is None

    def test_delete_nonexistent_is_safe(self, cache):
        cache.delete("does-not-exist")  # should not raise

    def test_invalidate_source(self, cache):
        cache.set("s1/a", data={}, source="source1")
        cache.set("s1/b", data={}, source="source1")
        cache.set("s2/a", data={}, source="source2")
        deleted = cache.invalidate_source("source1")
        assert deleted == 2
        assert cache.get("s1/a") is None
        assert cache.get("s1/b") is None
        assert cache.get("s2/a") is not None  # other source untouched


# ---------------------------------------------------------------------------
# APICache query tests
# ---------------------------------------------------------------------------

class TestAPICacheQueries:
    def test_list_by_source(self, cache):
        cache.set("cam/1", data={"id": 1}, source="camara_deputados")
        cache.set("cam/2", data={"id": 2}, source="camara_deputados")
        cache.set("sen/1", data={"id": 3}, source="senado_senadores")

        results = cache.list_by_source("camara_deputados")
        assert len(results) == 2
        assert all(e.source == "camara_deputados" for e in results)

    def test_stats_empty(self, cache):
        assert cache.stats() == {}

    def test_stats_populated(self, cache):
        cache.set("a/1", data={}, source="camara_deputados")
        cache.set("a/2", data={}, source="camara_deputados")
        cache.set("b/1", data={}, source="senado_senadores")

        stats = cache.stats()
        assert stats["camara_deputados"]["count"] == 2
        assert stats["senado_senadores"]["count"] == 1

    def test_stale_keys(self, cache):
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)
        fresh = dt.datetime.now(dt.timezone.utc)
        cache.set("old/key", data={}, source="camara_deputados")
        # Manually overwrite with old timestamp
        cache._db["api_cache"].update("old/key", {"fetched_at": old.isoformat()})
        cache.set("fresh/key", data={}, source="camara_deputados")

        stale = cache.stale_keys("camara_deputados", ttl_seconds=3600)
        assert "old/key" in stale
        assert "fresh/key" not in stale


# ---------------------------------------------------------------------------
# Snapshot tests
# ---------------------------------------------------------------------------

class TestAPICacheSnapshot:
    def test_export_snapshot(self, cache, tmp_path):
        cache.set("k1", data={"x": 1}, source="s")
        cache.set("k2", data={"x": 2}, source="s")

        out = tmp_path / "snap.json.gz"
        path = cache.export_snapshot(output_path=out)
        assert path.exists()

        with gzip.open(str(path), "rt") as f:
            payload = json.load(f)
        assert payload["total_records"] == 2
        assert len(payload["records"]) == 2

    def test_import_snapshot(self, cache, tmp_path):
        # Build a snapshot manually
        records = [
            {"key": "x/1", "source": "s", "data_json": '{"a":1}', "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(), "schema_version": "1"},
            {"key": "x/2", "source": "s", "data_json": '{"a":2}', "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(), "schema_version": "1"},
        ]
        snap = tmp_path / "snap.json.gz"
        with gzip.open(str(snap), "wt") as f:
            json.dump({"exported_at": "2026-01-01T00:00:00", "total_records": 2, "records": records}, f)

        count = cache.import_snapshot(snap)
        assert count == 2
        assert cache.get("x/1") is not None
        assert cache.get("x/1").data == {"a": 1}

    def test_export_creates_snapshots_dir(self, tmp_path):
        db_path = tmp_path / "cache.db"
        cache = APICache(db_path=db_path)
        cache.set("k", data={}, source="s")
        path = cache.export_snapshot()  # default path
        assert path.exists()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestAPICacheContextManager:
    def test_context_manager(self, tmp_path):
        with APICache(db_path=tmp_path / "ctx.db") as c:
            c.set("k", data={}, source="s")
            assert c.get("k") is not None
