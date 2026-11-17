"""Buyer summary, top suppliers and signal mix."""

from __future__ import annotations

from typing import Any

from veedor.domain.masking import NATURAL_PERSON, kind_from_ruc
from veedor.use_cases.queries._cache import VersionedCache
from veedor.use_cases.queries.catalogue import signal_label
from veedor.use_cases.queries.ports import LakePort, NotFoundError

TOP_SUPPLIERS = 10
_TABLES = ("process_scores",)


_CACHE = VersionedCache(max_entries=512)


def get_buyer(lake: LakePort, ruc: str) -> dict[str, Any]:
    """Buyer summary, memoised per data build (three aggregates over process_scores). Callers only read."""
    return _CACHE.get_or_compute(ruc, lake.data_version(), lambda: _build_buyer(lake, ruc))


def _build_buyer(lake: LakePort, ruc: str) -> dict[str, Any]:
    if kind_from_ruc(ruc) == NATURAL_PERSON:
        raise NotFoundError("buyer", ruc)  # same answer as an unknown buyer
    summary = lake.fetch(
        "SELECT any_value(buyer_name) AS name, count(*) AS n_processes, "
        "count(*) FILTER (WHERE n_signals > 0) AS n_flagged, sum(award_total) AS total_awarded, "
        "avg(risk_score) AS mean_risk_score, min(year) AS first_year, max(year) AS last_year "
        "FROM process_scores WHERE buyer_ruc = ?",
        [ruc],
        tables=_TABLES,
    )[0]
    if not summary["n_processes"]:
        raise NotFoundError("buyer", ruc)
    total = summary["total_awarded"]
    suppliers = lake.fetch(
        "SELECT winner_ruc AS ruc, any_value(winner_name) AS name, any_value(winner_kind) AS kind, "
        "count(*) AS n_awards, sum(award_total) AS total_awarded, avg(risk_score) AS mean_risk_score "
        "FROM process_scores WHERE buyer_ruc = ? AND winner_ruc IS NOT NULL "
        "GROUP BY winner_ruc ORDER BY total_awarded DESC NULLS LAST, n_awards DESC, winner_ruc "
        "LIMIT ?",
        [ruc, TOP_SUPPLIERS],
        tables=_TABLES,
    )
    mix = lake.fetch(
        "SELECT code, count(*) AS count FROM "
        "(SELECT unnest(signal_codes) AS code FROM process_scores WHERE buyer_ruc = ?) GROUP BY code "
        "ORDER BY count DESC, code",
        [ruc],
        tables=_TABLES,
    )
    return {
        "ruc": ruc,
        **summary,
        "top_suppliers": [
            {
                **s,
                "share_of_awarded": (s["total_awarded"] / total)
                if total and s["total_awarded"] is not None
                else None,
            }
            for s in suppliers
        ],
        "signal_mix": [{**m, "label_es": signal_label(m["code"])} for m in mix],
    }
