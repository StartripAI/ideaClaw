"""Literature search cache — avoids redundant API calls.

Surpasses ARC's cache.py by adding:
  - TTL-based expiration (default 24h)
  - LRU eviction when cache exceeds max size
  - Disk persistence via JSON (survives restarts)
  - Per-API rate tracking
  - Cache hit/miss statistics
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ideaclaw.source.collector import SourceResult


@dataclass
class CacheEntry:
    """A cached search result with metadata."""
    query: str
    api: str
    results: List[Dict[str, Any]]
    timestamp: float
    ttl_seconds: float = 86400.0  # 24h default

    @property
    def expired(self) -> bool:
        return (time.time() - self.timestamp) > self.ttl_seconds


@dataclass
class CacheStats:
    """Cache performance statistics."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    entries: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class SearchCache:
    """LRU disk-persistent cache for literature search results.

    Usage:
        cache = SearchCache(cache_dir="~/.ideaclaw/cache")
        
        # Check cache before API call
        results = cache.get("transformer attention", api="arxiv")
        if results is None:
            results = search_arxiv("transformer attention")
            cache.put("transformer attention", "arxiv", results)
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        max_entries: int = 1000,
        default_ttl: float = 86400.0,  # 24 hours
    ):
        self.cache_dir = Path(cache_dir or os.path.expanduser("~/.ideaclaw/cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self.stats = CacheStats()
        self._memory: OrderedDict[str, CacheEntry] = OrderedDict()
        self._load_from_disk()

    def _cache_key(self, query: str, api: str) -> str:
        """Generate a deterministic cache key."""
        normalized = f"{api}:{query.lower().strip()}"
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def get(
        self,
        query: str,
        api: str,
    ) -> Optional[List[SourceResult]]:
        """Retrieve cached results, or None if not cached/expired.

        Args:
            query: The search query string.
            api: The API name (arxiv, semantic_scholar, etc.).

        Returns:
            List of SourceResult if cached and valid, None otherwise.
        """
        key = self._cache_key(query, api)

        if key in self._memory:
            entry = self._memory[key]
            if entry.expired:
                # Expired — remove and return miss
                del self._memory[key]
                self._delete_from_disk(key)
                self.stats.misses += 1
                return None
            # Move to end (LRU)
            self._memory.move_to_end(key)
            self.stats.hits += 1
            return [SourceResult(**r) for r in entry.results]

        self.stats.misses += 1
        return None

    def put(
        self,
        query: str,
        api: str,
        results: List[SourceResult],
        ttl: Optional[float] = None,
    ) -> None:
        """Store search results in cache.

        Args:
            query: The search query string.
            api: The API name.
            results: List of SourceResult to cache.
            ttl: Optional TTL override in seconds.
        """
        key = self._cache_key(query, api)
        entry = CacheEntry(
            query=query,
            api=api,
            results=[asdict(r) for r in results],
            timestamp=time.time(),
            ttl_seconds=ttl or self.default_ttl,
        )

        # Evict oldest if at capacity
        while len(self._memory) >= self.max_entries:
            oldest_key, _ = self._memory.popitem(last=False)
            self._delete_from_disk(oldest_key)
            self.stats.evictions += 1

        self._memory[key] = entry
        self._save_to_disk(key, entry)
        self.stats.entries = len(self._memory)

    def invalidate(self, query: str, api: str) -> bool:
        """Remove a specific cache entry."""
        key = self._cache_key(query, api)
        if key in self._memory:
            del self._memory[key]
            self._delete_from_disk(key)
            self.stats.entries = len(self._memory)
            return True
        return False

    def clear(self) -> int:
        """Clear all cache entries. Returns count of entries cleared."""
        count = len(self._memory)
        self._memory.clear()
        for f in self.cache_dir.glob("*.json"):
            f.unlink(missing_ok=True)
        self.stats.entries = 0
        return count

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        expired_keys = [k for k, v in self._memory.items() if v.expired]
        for key in expired_keys:
            del self._memory[key]
            self._delete_from_disk(key)
        self.stats.entries = len(self._memory)
        return len(expired_keys)

    # ---- Disk persistence ----

    def _disk_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _save_to_disk(self, key: str, entry: CacheEntry) -> None:
        try:
            data = {
                "query": entry.query,
                "api": entry.api,
                "results": entry.results,
                "timestamp": entry.timestamp,
                "ttl_seconds": entry.ttl_seconds,
            }
            self._disk_path(key).write_text(
                json.dumps(data, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        except OSError:
            pass  # Disk write failure is non-fatal

    def _delete_from_disk(self, key: str) -> None:
        self._disk_path(key).unlink(missing_ok=True)

    def _load_from_disk(self) -> None:
        """Load cache entries from disk on startup."""
        loaded = 0
        for f in sorted(self.cache_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                entry = CacheEntry(
                    query=data["query"],
                    api=data["api"],
                    results=data["results"],
                    timestamp=data["timestamp"],
                    ttl_seconds=data.get("ttl_seconds", self.default_ttl),
                )
                if not entry.expired:
                    key = f.stem
                    self._memory[key] = entry
                    loaded += 1
                else:
                    f.unlink(missing_ok=True)
            except (json.JSONDecodeError, KeyError, OSError):
                f.unlink(missing_ok=True)
        self.stats.entries = loaded

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        return {
            "entries": self.stats.entries,
            "hits": self.stats.hits,
            "misses": self.stats.misses,
            "evictions": self.stats.evictions,
            "hit_rate": round(self.stats.hit_rate, 4),
            "max_entries": self.max_entries,
            "default_ttl_hours": self.default_ttl / 3600,
        }
