"""
SQLite-backed API response cache with TTL and offline fallback.

Design:
  - Every external API response is stored with a timestamp.
  - On read: if the record is fresher than TTL → return cached value.
  - On read: if stale AND network available → re-fetch, update cache, return.
  - On read: if stale AND network unavailable → return stale with warning (offline mode).
  - Snapshots: full JSON export of the cache for portability/backup.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import sqlite_utils

logger = logging.getLogger(__name__)

# Default TTLs (seconds)
DEFAULT_TTL = {
    "camara_deputados": 86_400,      # 24 hours — deputy info changes rarely
    "camara_votos": 3_600,           # 1 hour — votes updated more often
    "camara_proposicoes": 43_200,    # 12 hours
    "senado_senadores": 86_400,      # 24 hours
    "senado_votos": 3_600,           # 1 hour
    "tse_candidatos": 604_800,       # 1 week — election data is historical
    "rss": 1_800,                    # 30 min — news refreshes often
    "default": 3_600,                # 1 hour fallback
}

_CACHE_DB_PATH = Path(os.getenv("OUTPUT_DIR", "output")) / "api_cache.db"
_TABLE = "api_cache"


class CacheEntry:
    """Represents a single cached API response."""

    def __init__(
        self,
        key: str,
        source: str,
        data: Any,
        fetched_at: dt.datetime,
        schema_version: str = "1",
    ):
        self.key = key
        self.source = source
        self.data = data
        self.fetched_at = fetched_at
        self.schema_version = schema_version

    @property
    def age_seconds(self) -> float:
        now = dt.datetime.now(dt.timezone.utc)
        if self.fetched_at.tzinfo is None:
            fetched = self.fetched_at.replace(tzinfo=dt.timezone.utc)
        else:
            fetched = self.fetched_at
        return (now - fetched).total_seconds()

    def is_fresh(self, ttl_seconds: Optional[int] = None) -> bool:
        if ttl_seconds is None:
            ttl_seconds = DEFAULT_TTL.get("default", 3_600)
        return self.age_seconds < ttl_seconds

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "source": self.source,
            "data_json": json.dumps(self.data, ensure_ascii=False),
            "fetched_at": self.fetched_at.isoformat(),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_row(cls, row: dict) -> "CacheEntry":
        return cls(
            key=row["key"],
            source=row["source"],
            data=json.loads(row["data_json"]),
            fetched_at=dt.datetime.fromisoformat(row["fetched_at"]),
            schema_version=row.get("schema_version", "1"),
        )


class APICache:
    """
    Persistent SQLite cache for external API responses.

    Usage:
        cache = APICache()
        entry = cache.get("camara/deputados/12345", source="camara_deputados")
        if entry and entry.is_fresh():
            return entry.data
        # ... fetch from API ...
        cache.set("camara/deputados/12345", data=response, source="camara_deputados")
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or _CACHE_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite_utils.Database(str(self._db_path))
        self._ensure_table()

    def _ensure_table(self) -> None:
        if _TABLE not in self._db.table_names():
            self._db[_TABLE].create(
                {
                    "key": str,
                    "source": str,
                    "data_json": str,
                    "fetched_at": str,
                    "schema_version": str,
                },
                pk="key",
            )
            self._db[_TABLE].create_index(["source"], if_not_exists=True)
            self._db[_TABLE].create_index(["fetched_at"], if_not_exists=True)

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[CacheEntry]:
        """Return a cached entry by key, or None if not found."""
        try:
            row = self._db[_TABLE].get(key)
            return CacheEntry.from_row(dict(row))
        except Exception:
            return None

    def set(
        self,
        key: str,
        data: Any,
        source: str,
        schema_version: str = "1",
    ) -> CacheEntry:
        """Store a response in the cache. Overwrites any existing entry."""
        entry = CacheEntry(
            key=key,
            source=source,
            data=data,
            fetched_at=dt.datetime.now(dt.timezone.utc),
            schema_version=schema_version,
        )
        self._db[_TABLE].insert(entry.to_dict(), replace=True)
        return entry

    def delete(self, key: str) -> None:
        """Remove a single entry."""
        try:
            self._db[_TABLE].delete(key)
        except Exception:
            pass

    def invalidate_source(self, source: str) -> int:
        """Delete all cached entries for a given source. Returns count deleted."""
        rows = list(self._db[_TABLE].rows_where("source = ?", [source]))
        for row in rows:
            self._db[_TABLE].delete(row["key"])
        return len(rows)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_by_source(self, source: str) -> list[CacheEntry]:
        rows = self._db[_TABLE].rows_where("source = ?", [source])
        return [CacheEntry.from_row(dict(r)) for r in rows]

    def stats(self) -> dict[str, dict]:
        """Return per-source stats: count, oldest, newest."""
        result: dict[str, dict] = {}
        for row in self._db[_TABLE].rows:
            src = row["source"]
            if src not in result:
                result[src] = {"count": 0, "oldest": row["fetched_at"], "newest": row["fetched_at"]}
            result[src]["count"] += 1
            if row["fetched_at"] < result[src]["oldest"]:
                result[src]["oldest"] = row["fetched_at"]
            if row["fetched_at"] > result[src]["newest"]:
                result[src]["newest"] = row["fetched_at"]
        return result

    def stale_keys(self, source: str, ttl_seconds: Optional[int] = None) -> list[str]:
        """Return keys that are older than TTL for a given source."""
        if ttl_seconds is None:
            ttl_seconds = DEFAULT_TTL.get(source, DEFAULT_TTL["default"])
        entries = self.list_by_source(source)
        return [e.key for e in entries if not e.is_fresh(ttl_seconds)]

    # ------------------------------------------------------------------
    # Snapshot (backup/export)
    # ------------------------------------------------------------------

    def export_snapshot(self, output_path: Optional[Path] = None) -> Path:
        """
        Export the full cache to a gzipped JSON file.
        Default path: output/snapshots/cache_YYYYMMDD_HHMMSS.json.gz
        """
        if output_path is None:
            snapshots_dir = self._db_path.parent / "snapshots"
            snapshots_dir.mkdir(parents=True, exist_ok=True)
            ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_path = snapshots_dir / f"cache_{ts}.json.gz"

        all_rows = list(self._db[_TABLE].rows)
        payload = {
            "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "total_records": len(all_rows),
            "records": all_rows,
        }
        with gzip.open(str(output_path), "wt", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.info("Cache snapshot exported: %s (%d records)", output_path, len(all_rows))
        return output_path

    def import_snapshot(self, snapshot_path: Path) -> int:
        """
        Import a previously exported snapshot into the cache.
        Existing records with the same key are overwritten.
        Returns number of records imported.
        """
        with gzip.open(str(snapshot_path), "rt", encoding="utf-8") as f:
            payload = json.load(f)

        records = payload.get("records", [])
        for row in records:
            self._db[_TABLE].insert(row, replace=True)

        logger.info("Cache snapshot imported: %d records from %s", len(records), snapshot_path)
        return len(records)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "APICache":
        return self

    def __exit__(self, *_) -> None:
        pass  # sqlite-utils handles connection cleanup


# ---------------------------------------------------------------------------
# Module-level singleton helpers
# ---------------------------------------------------------------------------

_default_cache: Optional[APICache] = None


def get_cache(db_path: Optional[Path] = None) -> APICache:
    """Return the default module-level cache instance (created on first call)."""
    global _default_cache
    if _default_cache is None or db_path is not None:
        _default_cache = APICache(db_path=db_path)
    return _default_cache
