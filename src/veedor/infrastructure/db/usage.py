"""Shared usage counters of the question route, in the database the API already uses.

``consume(bucket, limit)`` is one atomic statement: it inserts the bucket with ``used = 1`` or increments it
only while ``used < limit``, and says whether it counted. Every worker process and every restart sees the
same counters, which the in-memory limiters (per worker, reset on restart) cannot. The SQL is also valid on
SQLite 3.35 or later, which the unit tests use.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, text

RETENTION = timedelta(days=2)
PRUNE_PROBABILITY = 0.01

_CONSUME = text(
    "INSERT INTO ask_usage (bucket, used, updated_at) VALUES (:bucket, 1, :now) "
    "ON CONFLICT (bucket) DO UPDATE SET used = ask_usage.used + 1, updated_at = :now "
    "WHERE ask_usage.used < :limit RETURNING used"
)
_USED = text("SELECT used FROM ask_usage WHERE bucket = :bucket")
_PRUNE = text("DELETE FROM ask_usage WHERE updated_at < :cutoff")


class AskUsageStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def consume(self, bucket: str, limit: int) -> bool:
        """True when one unit of `bucket` was counted, False when `limit` units were already used.
        Raises on a database error: the caller decides the fallback."""
        if limit <= 0:
            return False
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = connection.execute(_CONSUME, {"bucket": bucket, "limit": limit, "now": now}).first()
            if random.random() < PRUNE_PROBABILITY:  # noqa: S311 - not a secret
                connection.execute(_PRUNE, {"cutoff": now - RETENTION})
        return row is not None

    def used(self, bucket: str) -> int:
        with self._engine.connect() as connection:
            row = connection.execute(_USED, {"bucket": bucket}).first()
        return int(row[0]) if row else 0
