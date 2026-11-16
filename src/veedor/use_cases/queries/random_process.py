"""A process chosen uniformly at random among those the API can show.

Why pools and not ``ORDER BY random()``. Sorting 2.25 M rows on every call would make the route
expensive to hammer. Instead, for each filter combination one uniform random sample of
``POOL_SIZE`` matching rows is drawn from the lake (one scan, once) and kept in memory; each call
removes one row from it, chosen with ``secrets``. A uniform subset, drawn without replacement,
gives every matching process the same probability on every call; when the pool is empty a fresh
independent sample is drawn. Pools are bounded (``MAX_POOLS``), keyed by the data build version,
and a call costs no database work while its pool has rows.

Matches: processes whose identifier the API accepts (the path pattern of ``/processes/{ocid}``),
whose winner has a company or public-entity RUC (third digit 9 or 6, 13 ASCII digits) and whose
buyer is not a natural person. Natural-person winners, winners without a RUC and natural-person
buyers are never candidates.
"""

from __future__ import annotations

import math
import secrets
import threading
import time
from typing import Any

from veedor.use_cases.queries._cache import VersionedCache
from veedor.use_cases.queries.ports import LakePort, NotFoundError, Row

POOL_SIZE = 1000
MAX_POOLS = 32
EMPTY_RETRY_SECONDS = 30.0  # a combination that matched nothing is not scanned again for this long
_TABLES = ("process_scores",)

ELIGIBLE = (
    "regexp_full_match(ocid, '^ocds-5wno2w-[A-Za-z0-9._-]{1,120}$') "
    "AND winner_ruc IS NOT NULL AND regexp_full_match(winner_ruc, '[0-9]{13}') "
    "AND substr(winner_ruc, 3, 1) IN ('6', '9') "
    "AND NOT (buyer_ruc IS NOT NULL AND length(buyer_ruc) IN (10, 13) "
    "AND substr(buyer_ruc, 3, 1) IN ('0', '1', '2', '3', '4', '5'))"
)
_SIGNAL_CLAUSES = {True: " AND n_signals > 0", False: " AND (n_signals = 0 OR n_signals IS NULL)", None: ""}

_POOLS = VersionedCache(max_entries=MAX_POOLS)


class _Pool:
    """Rows still unserved from one uniform sample, drawn without replacement.

    When the sample returned fewer rows than asked for it IS the whole match set (`complete`), so
    it is refilled from memory without scanning the lake again.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.rows: list[Row] = []
        self.complete: list[Row] | None = None
        self.empty_until = 0.0


def pick_random_process(lake: LakePort, *, with_signals: bool | None, min_score: float | None) -> Row:
    """One uniformly chosen `process_scores` row; `NotFoundError` when nothing matches.

    `with_signals`: True only processes with at least one risk signal, False only those without,
    None either. `min_score` keeps rows with ``risk_score >= min_score``.
    """
    floor = None if min_score is None else max(0, math.floor(min_score))
    version = lake.data_version()
    pool: _Pool = _POOLS.get_or_compute((with_signals, floor), version, _Pool)
    with pool.lock:
        row = _draw(pool, min_score)
        if row is None and time.monotonic() >= pool.empty_until:
            _refill(pool, lake, with_signals, floor)
            row = _draw(pool, min_score)
            if row is None:
                pool.empty_until = time.monotonic() + EMPTY_RETRY_SECONDS
    if row is None:
        raise NotFoundError("process", "random")
    return row


def _refill(pool: _Pool, lake: LakePort, with_signals: bool | None, floor: int | None) -> None:
    if pool.complete is not None:
        pool.rows = list(pool.complete)
        return
    pool.rows = _sample(lake, with_signals, floor)
    if len(pool.rows) < POOL_SIZE:
        pool.complete = list(pool.rows)


def _draw(pool: _Pool, min_score: float | None) -> Row | None:
    """Remove and return a uniformly chosen row that satisfies the exact threshold."""
    usable = [
        index
        for index, row in enumerate(pool.rows)
        if min_score is None or (row["risk_score"] is not None and row["risk_score"] >= min_score)
    ]
    if not usable:
        return None
    index = usable[secrets.randbelow(len(usable))]
    pool.rows[index], pool.rows[-1] = pool.rows[-1], pool.rows[index]
    return pool.rows.pop()


def _sample(lake: LakePort, with_signals: bool | None, floor: int | None) -> list[Row]:
    params: list[Any] = []
    where = ELIGIBLE + _SIGNAL_CLAUSES[with_signals]
    if floor is not None:
        where += " AND risk_score >= ?"
        params.append(floor)
    sql = (
        f"SELECT * FROM (SELECT * FROM process_scores WHERE {where}) "
        f"USING SAMPLE reservoir({int(POOL_SIZE)} ROWS)"
    )
    return lake.fetch(sql, params, tables=_TABLES)
