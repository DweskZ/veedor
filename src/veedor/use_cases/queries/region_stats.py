"""Per-province aggregates over the buying entity's province, and the raw-value catalogue.

Basis. A "competitive process" is a row of ``processes`` with ``method_group = 'competitive'``.
``with_signal`` counts competitive processes whose ``process_scores.n_signals`` is above zero (risk
signals only; context signals never count), ``single_bidder`` those whose risk signals include
``SINGLE_BIDDER``. Percentages use all competitive processes of the province as denominator.
Everything is one aggregate over the lake, computed once per data build and cached.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from veedor.domain.regions import (
    NATIONAL,
    NATIONAL_LABEL,
    SIN_REGION,
    canonical_region,
    region_label,
)
from veedor.use_cases.queries._cache import VersionedCache
from veedor.use_cases.queries.ports import LakePort

logger = logging.getLogger(__name__)

SMALL_SAMPLE_LIMIT = 500  # fewer competitive processes than this: flagged `small_sample`
_TABLES = ("processes", "process_scores")
_CACHE = VersionedCache(max_entries=4)
_RAW_CACHE = VersionedCache(max_entries=4)

# One SELECT: one row per distinct raw `buyer_region`, sums only (merged in code after normalising).
REGION_AGGREGATE_SQL = """
SELECT p.buyer_region AS raw_region,
       count(*) AS processes_total,
       count(*) FILTER (WHERE p.method_group = 'competitive') AS competitive_processes,
       count(*) FILTER (WHERE p.method_group = 'competitive' AND s.n_signals > 0) AS with_signal,
       count(*) FILTER (
           WHERE p.method_group = 'competitive' AND list_contains(s.signal_codes, 'SINGLE_BIDDER')
       ) AS single_bidder,
       sum(s.risk_score) FILTER (WHERE p.method_group = 'competitive') AS score_sum,
       count(s.risk_score) FILTER (WHERE p.method_group = 'competitive') AS score_count,
       sum(s.award_total) AS awarded_total
FROM processes p LEFT JOIN process_scores s ON s.ocid = p.ocid
GROUP BY p.buyer_region
"""

_SUM_FIELDS = (
    "processes_total",
    "competitive_processes",
    "with_signal",
    "single_bidder",
    "score_sum",
    "score_count",
    "awarded_total",
)


def get_region_stats(lake: LakePort) -> dict[str, Any]:
    """`GET /stats/by-region` payload, memoised per data build."""
    version = lake.data_version()
    return _CACHE.get_or_compute("regions", version, lambda: _compute(lake))


def region_raw_values(lake: LakePort, key: str) -> list[str]:
    """The exact ``buyer_region`` strings in the lake that mean the canonical `key` (never NULL).

    Used to filter by region with plain equality instead of a function over the whole column.
    """
    version = lake.data_version()
    catalogue = _RAW_CACHE.get_or_compute("raw", version, lambda: _raw_catalogue(lake))
    return catalogue.get(key, [])


def _raw_catalogue(lake: LakePort) -> dict[str, list[str]]:
    rows = lake.fetch(
        "SELECT DISTINCT buyer_region AS raw_region FROM processes WHERE buyer_region IS NOT NULL",
        tables=("processes",),
    )
    catalogue: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        catalogue[canonical_region(row["raw_region"]) or SIN_REGION].append(row["raw_region"])
    return dict(catalogue)


def _compute(lake: LakePort) -> dict[str, Any]:
    rows = lake.fetch(REGION_AGGREGATE_SQL, tables=_TABLES)
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = canonical_region(row["raw_region"])
        if key is None:
            logger.warning("Unrecognised buyer_region %r counted as %s", row["raw_region"], SIN_REGION)
            key = SIN_REGION
        bucket = merged.setdefault(key, dict.fromkeys(_SUM_FIELDS, 0))
        for field in _SUM_FIELDS:
            bucket[field] += row[field] or 0
    national = dict.fromkeys(_SUM_FIELDS, 0)
    for bucket in merged.values():
        for field in _SUM_FIELDS:
            national[field] += bucket[field]
    ordered = sorted(merged, key=lambda k: (k == SIN_REGION, region_label(k).casefold()))
    return {
        "items": [_item(key, region_label(key), merged[key]) for key in ordered],
        "national": _item(NATIONAL, NATIONAL_LABEL, national, national_row=True),
        "basis": "competitive",
        "data_built_at": lake.built_at(),
        "notes": [
            "La provincia es la de la entidad contratante, no la del lugar donde se ejecuta el contrato.",
            "Los porcentajes se calculan sobre los procesos competitivos de cada provincia.",
        ],
    }


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 2) if whole else None


def _item(key: str, label: str, sums: dict[str, Any], *, national_row: bool = False) -> dict[str, Any]:
    competitive = int(sums["competitive_processes"])
    return {
        "region": key,
        "region_label": label,
        "competitive_processes": competitive,
        "with_signal": int(sums["with_signal"]),
        "pct_with_signal": _pct(int(sums["with_signal"]), competitive),
        "single_bidder": int(sums["single_bidder"]),
        "pct_single_bidder": _pct(int(sums["single_bidder"]), competitive),
        "mean_score": round(sums["score_sum"] / sums["score_count"], 2) if sums["score_count"] else None,
        "processes_total": int(sums["processes_total"]),
        "awarded_total": round(float(sums["awarded_total"]), 2),
        "small_sample": (not national_row) and competitive < SMALL_SAMPLE_LIMIT,
    }
