"""Buyer-name lookup in the lake (the vector table stores the buyer RUC only)."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from veedor.core.settings import get_settings
from veedor.infrastructure.lake.reader import LakeReader
from veedor.use_cases.queries.ports import LakePort, LakeUnavailableError

logger = logging.getLogger(__name__)
_CACHE: dict[str, str] = {}
_MAX_CACHE = 50_000


def buyer_names_from(lake: LakePort, rucs: Sequence[str]) -> dict[str, str]:
    """Names for the given buyer RUCs; unknown RUCs and an unavailable lake simply yield no name."""
    if not rucs:
        return {}
    table = "process_scores" if lake.has_table("process_scores") else "processes"
    placeholders = ", ".join("?" for _ in rucs)
    sql = (
        f"SELECT buyer_ruc, buyer_name, count(*) AS n FROM {table} "
        f"WHERE buyer_ruc IN ({placeholders}) AND buyer_name IS NOT NULL GROUP BY buyer_ruc, buyer_name"
    )
    try:
        rows = lake.fetch(sql, list(rucs), tables=(table,))
    except LakeUnavailableError:
        logger.warning("Lake unavailable: buyer names omitted from similar-process results")
        return {}
    return most_frequent_names(rows)


def most_frequent_names(rows: Sequence[Mapping[str, object]]) -> dict[str, str]:
    """One name per RUC: the most frequent spelling, ties broken by the smallest name (deterministic,
    so two requests, two workers or two cache states can never disagree)."""
    best: dict[str, tuple[int, str]] = {}
    for row in rows:
        ruc, name, count = str(row["buyer_ruc"]), str(row["buyer_name"]), int(row["n"])  # type: ignore[call-overload]
        current = best.get(ruc)
        if current is None or (-count, name) < (-current[0], current[1]):
            best[ruc] = (count, name)
    return {ruc: name for ruc, (_, name) in best.items()}


def lake_buyer_names(rucs: Sequence[str]) -> Mapping[str, str]:
    """Process-wide cached lookup used by `find_similar` when no lookup is injected."""
    missing = [ruc for ruc in rucs if ruc not in _CACHE]
    if missing:
        settings = get_settings()
        if len(_CACHE) > _MAX_CACHE:
            _CACHE.clear()
        _CACHE.update(buyer_names_from(LakeReader(settings.lake_dir, settings.marts_dir), missing))
    return {ruc: _CACHE[ruc] for ruc in rucs if ruc in _CACHE}
