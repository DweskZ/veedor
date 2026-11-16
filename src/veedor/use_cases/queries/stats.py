"""Dashboard statistics."""

from __future__ import annotations

import threading
from typing import Any

from veedor.use_cases.queries.catalogue import signal_kind, signal_label
from veedor.use_cases.queries.ports import LakePort

_TABLES = ("process_scores", "process_signals")
_cache_lock = threading.Lock()
_cached: tuple[str, dict[str, Any]] | None = None


def get_stats_cached(lake: LakePort) -> dict[str, Any]:
    """`get_stats` memoised per process; the entry is keyed by the lake's data version, so a
    rebuilt table is never served stale. Concurrent callers wait for one computation."""
    global _cached
    version = lake.data_version()
    with _cache_lock:
        if _cached is None or _cached[0] != version:
            _cached = (version, get_stats(lake))
        return dict(_cached[1])  # shallow copy: callers may add top-level keys


def get_stats(lake: LakePort) -> dict[str, Any]:
    scored = lake.fetch(
        "SELECT count(*) AS n, count(*) FILTER (WHERE n_signals > 0) AS flagged, "
        "avg(risk_score) AS mean_score, min(year) AS first_year, max(year) AS last_year "
        "FROM process_scores",
        tables=_TABLES,
    )[0]
    buckets = lake.fetch(
        "SELECT least(CAST(floor(risk_score / 10) AS INTEGER), 9) AS bucket, count(*) AS n "
        "FROM process_scores GROUP BY 1 ORDER BY 1",
        tables=_TABLES,
    )
    signal_counts = lake.fetch(
        "SELECT signal_code AS code, count(*) AS count FROM process_signals GROUP BY 1 ORDER BY 2 DESC, 1",
        tables=_TABLES,
    )
    stats: dict[str, Any] = {
        "processes_scored": scored["n"],
        "processes_with_signals": scored["flagged"],
        "mean_risk_score": scored["mean_score"],
        "first_year": scored["first_year"],
        "last_year": scored["last_year"],
        "score_distribution": [
            {"lower": row["bucket"] * 10, "upper": row["bucket"] * 10 + 10, "count": row["n"]}
            for row in buckets
        ],
        # `signal_counts` lists risk signals only; context signals are reported separately.
        "signal_counts": _labelled(signal_counts, "risk"),
        "context_signal_counts": _labelled(signal_counts, "context"),
        "available_tables": {},
    }
    if lake.has_table("processes"):
        stats |= _lake_stats(lake)
    return stats


def _labelled(rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [
        {**row, "label_es": signal_label(row["code"]), "kind": kind}
        for row in rows
        if signal_kind(row["code"]) == kind
    ]


def _lake_stats(lake: LakePort) -> dict[str, Any]:
    totals = lake.fetch(
        "SELECT count(*) AS n, "
        "CAST(CAST(max(try_cast(release_date AS TIMESTAMPTZ)) AS DATE) AS VARCHAR) AS last_date "
        "FROM processes",
        tables=("processes",),
    )[0]
    groups = lake.fetch(
        "SELECT coalesce(method_group, 'unknown') AS grp, count(*) AS n FROM processes "
        "GROUP BY 1 ORDER BY 2 DESC",
        tables=("processes",),
    )
    return {
        "processes_total": totals["n"],
        "last_data_date": totals["last_date"],
        "processes_by_method_group": {row["grp"]: row["n"] for row in groups},
    }
