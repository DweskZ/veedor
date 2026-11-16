"""Where a process sits among the processes of the same method and year.

One group = every process with the same ``method`` and ``year``. Its distributions are computed in
one SELECT the first time a process of the group is asked about and kept (bounded, keyed by the data
build version). Definitions used throughout:

* number of tenderers: ``n_tenderers`` counted in the buckets 1, 2, 3, 4, 5 and 6 or more;
* award/budget ratio: ``award_total / budget`` for processes with ``budget > 0`` and ``award_total > 0``;
* tender window: days between ``tender_start`` and ``tender_end`` when both exist and the end is later;
* percentile of a value: the percentage of the group's processes (with that field) whose value is
  lower than or equal to it; quartiles use linear interpolation between the closest ranks.
"""

from __future__ import annotations

from array import array
from bisect import bisect_right
from dataclasses import dataclass
from typing import Any

from veedor.use_cases.queries._cache import VersionedCache
from veedor.use_cases.queries.ports import LakePort, NotFoundError

TENDERER_BUCKETS = ("1", "2", "3", "4", "5", "6+")
NOT_PUBLISHED = "not_published_for_procedure"
NOT_AVAILABLE = "not_available_for_process"
REASONS = {
    NOT_PUBLISHED: "Este tipo de procedimiento no publica este dato.",
    NOT_AVAILABLE: "Este proceso no tiene este dato en los datos publicados.",
}
MAX_CACHED_VALUES = 6_000_000  # sorted values kept across all cached groups (8 bytes each)
_TABLES = ("processes",)

PROCESS_SQL = (
    "SELECT method, year, n_tenderers, budget, award_total, "
    "(epoch(try_cast(tender_end AS TIMESTAMPTZ)) - epoch(try_cast(tender_start AS TIMESTAMPTZ))) / 86400.0 "
    "AS window_days FROM processes WHERE ocid = ?"
)
# One row per group: its size and the sorted ratio and window values.
GROUP_SQL = """
WITH g AS (
    SELECT n_tenderers,
           CASE WHEN budget > 0 AND award_total > 0 THEN award_total / budget END AS ratio,
           CASE WHEN try_cast(tender_end AS TIMESTAMPTZ) > try_cast(tender_start AS TIMESTAMPTZ)
                THEN (epoch(try_cast(tender_end AS TIMESTAMPTZ))
                      - epoch(try_cast(tender_start AS TIMESTAMPTZ))) / 86400.0 END AS days
    FROM processes WHERE method = ? AND year = ?
)
SELECT (SELECT count(*) FROM g) AS n_processes,
       (SELECT list(ratio ORDER BY ratio) FROM g WHERE ratio IS NOT NULL) AS ratios,
       (SELECT list(days ORDER BY days) FROM g WHERE days IS NOT NULL) AS windows
"""
TENDERER_COUNT_SQL = (
    "SELECT n_tenderers AS value, count(*) AS n FROM processes "
    "WHERE method = ? AND year = ? AND n_tenderers >= 1 GROUP BY n_tenderers"
)


@dataclass(frozen=True, slots=True)
class GroupStats:
    n_processes: int
    tenderer_counts: dict[int, int]
    ratios: array  # sorted
    windows: array  # sorted


_CACHE = VersionedCache(
    max_entries=256,
    max_weight=MAX_CACHED_VALUES,
    weigher=lambda g: len(g.ratios) + len(g.windows) + len(g.tenderer_counts) + 8,
)


def get_process_context(lake: LakePort, ocid: str) -> dict[str, Any]:
    rows = lake.fetch(PROCESS_SQL, [ocid], tables=_TABLES)
    if not rows:
        raise NotFoundError("process", ocid)
    process = rows[0]
    method, year = process["method"], process["year"]
    group = _group(lake, method, year) if method is not None and year is not None else None
    return {
        "ocid": ocid,
        "method": method,
        "year": year,
        "comparable_processes": group.n_processes if group else 0,
        "tenderers": _tenderers(process["n_tenderers"], group),
        "award_budget_ratio": _measure(_ratio(process), group.ratios if group else None),
        "tender_window_days": _measure(_window(process), group.windows if group else None, digits=1),
    }


def _group(lake: LakePort, method: str, year: int) -> GroupStats:
    def compute() -> GroupStats:
        row = lake.fetch(GROUP_SQL, [method, year], tables=_TABLES)[0]
        by_value = lake.fetch(TENDERER_COUNT_SQL, [method, year], tables=_TABLES)
        counts = {int(r["value"]): int(r["n"]) for r in by_value}
        return GroupStats(
            int(row["n_processes"]),
            counts,
            array("d", row["ratios"] or ()),
            array("d", row["windows"] or ()),
        )

    return _CACHE.get_or_compute((method, year), lake.data_version(), compute)


def _ratio(process: dict[str, Any]) -> float | None:
    budget, award = process["budget"], process["award_total"]
    return award / budget if budget is not None and award is not None and budget > 0 and award > 0 else None


def _window(process: dict[str, Any]) -> float | None:
    days = process["window_days"]
    return days if days is not None and days > 0 else None


def _bucket(counts: dict[int, int]) -> list[dict[str, Any]]:
    out = [{"bucket": str(n), "count": counts.get(n, 0)} for n in range(1, 6)]
    out.append({"bucket": "6+", "count": sum(c for n, c in counts.items() if n >= 6)})
    return out


def _tenderers(value: int | None, group: GroupStats | None) -> dict[str, Any]:
    counts = group.tenderer_counts if group else {}
    total = sum(counts.values())
    reason = None
    if total == 0:
        reason = NOT_PUBLISHED
    elif value is None or value < 1:
        reason = NOT_AVAILABLE
    percentile = None
    if reason is None and value is not None:
        percentile = round(100 * sum(c for n, c in counts.items() if n <= value) / total, 1)
    return {
        "value": value if reason is None else None,
        "percentile": percentile,
        "n": total,
        "distribution": _bucket(counts) if total else [],
        **_reason(reason),
    }


def _measure(value: float | None, sorted_values: array | None, *, digits: int = 4) -> dict[str, Any]:
    n = len(sorted_values) if sorted_values is not None else 0
    reason = NOT_PUBLISHED if n == 0 else (NOT_AVAILABLE if value is None else None)
    stats: dict[str, Any] = {"q1": None, "median": None, "q3": None}
    if sorted_values is not None and n:
        stats = {
            "q1": round(_quantile(sorted_values, 0.25), digits),
            "median": round(_quantile(sorted_values, 0.5), digits),
            "q3": round(_quantile(sorted_values, 0.75), digits),
        }
    percentile = None
    if reason is None and value is not None and sorted_values is not None:
        percentile = round(100 * bisect_right(sorted_values, value) / n, 1)
    return {
        "value": round(value, digits) if reason is None and value is not None else None,
        "percentile": percentile,
        "n": n,
        **stats,
        **_reason(reason),
    }


def _reason(code: str | None) -> dict[str, Any]:
    return {"reason_code": code, "reason": REASONS[code] if code else None}


def _quantile(values: array, fraction: float) -> float:
    """Linear interpolation between the closest ranks of an already sorted array."""
    position = (len(values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)
