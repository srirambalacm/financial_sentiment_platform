"""A small in-process TTL cache.

The evaluation endpoint builds a full date x ticker panel across the universe
and runs a parameter search — several seconds of pandas work over ~120K rows.
Recomputing that per request would make the dashboard unusable, so results are
memoized with a time-to-live.

Deliberately in-process and dependency-free: this is a single-instance read
-mostly API over a static SQLite file, and reaching for Redis here would add
an operational dependency to solve a problem that does not exist yet.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

DEFAULT_TTL_SECONDS = 3600.0


class TTLCache:
    """Thread-safe key/value cache with per-entry expiry."""

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS):
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Return the cached value, or None if missing or expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.time() >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.time() + self.ttl, value)

    def get_or_compute(self, key: str, factory: Callable[[], Any]) -> Any:
        """Return the cached value, computing and storing it on a miss.

        The factory runs outside the lock so a slow computation does not block
        reads of other keys. A concurrent duplicate computation is possible and
        accepted: it wastes a little work but never returns a wrong answer.
        """
        hit = self.get(key)
        if hit is not None:
            return hit
        value = factory()
        self.set(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        with self._lock:
            now = time.time()
            live = sum(1 for exp, _ in self._store.values() if exp > now)
            return {"entries": len(self._store), "live_entries": live, "ttl": self.ttl}


# Shared cache instance used by the API routes.
cache = TTLCache()