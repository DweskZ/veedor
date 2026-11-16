"""Process-local memoisation tagged with the data version of the lake.

An entry is valid only for the ``lake.data_version()`` it was computed under, so a marts rebuild
(any replaced table or build summary) makes every entry stale. Concurrent callers asking for the
same key wait for one computation; different keys compute in parallel. The cache is bounded by
entry count and, optionally, by a caller-defined weight.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any

_REGISTRY: list[VersionedCache] = []


class VersionedCache:
    def __init__(
        self,
        *,
        max_entries: int = 64,
        max_weight: int | None = None,
        weigher: Callable[[Any], int] | None = None,
    ) -> None:
        self._max_entries = max_entries
        self._max_weight = max_weight
        self._weigher = weigher or (lambda _: 1)
        self._lock = threading.Lock()
        self._entries: OrderedDict[Hashable, tuple[str, Any, int]] = OrderedDict()
        self._key_locks: dict[Hashable, threading.Lock] = {}
        _REGISTRY.append(self)

    def get_or_compute(self, key: Hashable, version: str, compute: Callable[[], Any]) -> Any:
        found = self._lookup(key, version)
        if found is not None:
            return found[0]
        with self._key_lock(key):
            found = self._lookup(key, version)  # another caller may have finished meanwhile
            if found is not None:
                return found[0]
            value = compute()
            self._store(key, version, value)
            return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._key_locks.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def _lookup(self, key: Hashable, version: str) -> tuple[Any] | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry[0] != version:
                return None
            self._entries.move_to_end(key)
            return (entry[1],)

    def _key_lock(self, key: Hashable) -> threading.Lock:
        with self._lock:
            return self._key_locks.setdefault(key, threading.Lock())

    def _store(self, key: Hashable, version: str, value: Any) -> None:
        weight = self._weigher(value)
        with self._lock:
            self._entries[key] = (version, value, weight)
            self._entries.move_to_end(key)
            total = sum(entry[2] for entry in self._entries.values())
            while len(self._entries) > 1 and (
                len(self._entries) > self._max_entries
                or (self._max_weight is not None and total > self._max_weight)
            ):
                _, (_, _, dropped) = self._entries.popitem(last=False)
                total -= dropped
            if len(self._key_locks) > 4 * self._max_entries:  # keep the lock table bounded
                for stale in [k for k, lock in self._key_locks.items() if not lock.locked()]:
                    del self._key_locks[stale]


def clear_all_caches() -> None:
    """Empty every cache (used by tests; a rebuilt lake needs no call, its version changes)."""
    for cache in _REGISTRY:
        cache.clear()
