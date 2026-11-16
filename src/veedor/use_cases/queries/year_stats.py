"""Per-year aggregates: volume, single-bidder reverse auctions, signals and the method mix.

Definitions (all over ``processes`` unless stated):

* ``processes_total``: every process of the year; ``competitive_processes``: ``method_group = 'competitive'``.
* ``pct_single_bidder``: among competitive processes whose method is Subasta Inversa Electrónica (the
  one procedure whose name is stable over the whole period) and whose number of tenderers is known,
  the share with exactly one tenderer.
* ``pct_with_signal``: among competitive processes, the share with at least one risk signal
  (``process_scores.n_signals > 0``).
* ``method_mix``: share of the awarded amount (``award_total``, null amounts excluded) by method group.
"""

from __future__ import annotations

from typing import Any

from veedor.use_cases.queries._cache import VersionedCache
from veedor.use_cases.queries.ports import LakePort

STABLE_METHOD = "Subasta Inversa Electrónica"
MIX_GROUPS = ("competitive", "direct", "catalogue", "other")
_TABLES = ("processes", "process_scores")
_CACHE = VersionedCache(max_entries=2)

NOTE_2022 = (
    "2022 tiene muchos menos procesos publicados que los años vecinos; las cifras de ese año se basan "
    "en menos procesos y deben leerse con cautela."
)
NOTE_NAMING = (
    "Alrededor de 2025 y 2026 cambian los nombres de los procedimientos: en 2026 ya no aparecen Menor "
    "Cuantía ni Cotización y aumenta Licitación. Por eso la serie de oferente único usa solo Subasta "
    "Inversa Electrónica, cuyo nombre es el mismo en todo el periodo."
)
NOTE_PARTIAL = (
    "El último año está incompleto: solo incluye los procesos publicados hasta la fecha de los datos."
)
NAMING_YEARS = (2025, 2026)
YEAR_NOTES = {2022: NOTE_2022, **dict.fromkeys(NAMING_YEARS, NOTE_NAMING)}

YEAR_AGGREGATE_SQL = """
SELECT p.year AS year,
       count(*) AS processes_total,
       count(*) FILTER (WHERE p.method_group = 'competitive') AS competitive_processes,
       count(*) FILTER (
           WHERE p.method_group = 'competitive' AND p.method = ? AND p.n_tenderers IS NOT NULL
       ) AS single_bidder_base,
       count(*) FILTER (
           WHERE p.method_group = 'competitive' AND p.method = ? AND p.n_tenderers = 1
       ) AS single_bidder_count,
       count(*) FILTER (WHERE p.method_group = 'competitive' AND s.n_signals > 0) AS with_signal,
       sum(p.award_total) AS awarded_total,
       sum(p.award_total) FILTER (WHERE p.method_group = 'competitive') AS amount_competitive,
       sum(p.award_total) FILTER (WHERE p.method_group = 'direct') AS amount_direct,
       sum(p.award_total) FILTER (WHERE p.method_group = 'catalogue') AS amount_catalogue,
       sum(p.award_total) FILTER (
           WHERE p.method_group IS NULL OR p.method_group NOT IN ('competitive', 'direct', 'catalogue')
       ) AS amount_other
FROM processes p LEFT JOIN process_scores s ON s.ocid = p.ocid
WHERE p.year IS NOT NULL
GROUP BY p.year ORDER BY p.year
"""
LAST_DATE_SQL = (
    "SELECT CAST(CAST(max(try_cast(release_date AS TIMESTAMPTZ)) AS DATE) AS VARCHAR) AS last_date "
    "FROM processes"
)


def get_year_stats(lake: LakePort) -> dict[str, Any]:
    """`GET /stats/by-year` payload, memoised per data build."""
    return _CACHE.get_or_compute("years", lake.data_version(), lambda: _compute(lake))


def _pct(part: float, whole: float) -> float | None:
    return round(100 * part / whole, 2) if whole else None


def _compute(lake: LakePort) -> dict[str, Any]:
    rows = lake.fetch(YEAR_AGGREGATE_SQL, [STABLE_METHOD, STABLE_METHOD], tables=_TABLES)
    last_date = lake.fetch(LAST_DATE_SQL, tables=("processes",))[0]["last_date"]
    last_year = rows[-1]["year"] if rows else None
    items = [_item(row, last_year, last_date) for row in rows]
    notes = [note for year, note in YEAR_NOTES.items() if any(i["year"] == year for i in items)]
    notes = list(dict.fromkeys(notes))
    if items and items[-1]["partial_year"]:
        notes.append(NOTE_PARTIAL)
    return {
        "items": items,
        "single_bidder_method": STABLE_METHOD,
        "notes": notes,
        "data_built_at": lake.built_at(),
    }


def _item(row: dict[str, Any], last_year: int | None, last_date: str | None) -> dict[str, Any]:
    year = int(row["year"])
    amounts = {
        "competitive": row["amount_competitive"] or 0.0,
        "direct": row["amount_direct"] or 0.0,
        "catalogue": row["amount_catalogue"] or 0.0,
        "other": row["amount_other"] or 0.0,
    }
    total = float(row["awarded_total"] or 0.0)
    partial = year == last_year and (last_date is None or last_date < f"{year}-12-31")
    notes = [YEAR_NOTES[year]] if year in YEAR_NOTES else []
    if partial:
        notes.append(NOTE_PARTIAL)
    return {
        "year": year,
        "processes_total": int(row["processes_total"]),
        "competitive_processes": int(row["competitive_processes"]),
        "single_bidder_base": int(row["single_bidder_base"]),
        "single_bidder_count": int(row["single_bidder_count"]),
        "pct_single_bidder": _pct(row["single_bidder_count"], row["single_bidder_base"]),
        "pct_with_signal": _pct(row["with_signal"], row["competitive_processes"]),
        "awarded_total": round(total, 2),
        "method_mix": {group: _pct(amounts[group], total) for group in MIX_GROUPS},
        "partial_year": partial,
        "notes": notes,
    }
