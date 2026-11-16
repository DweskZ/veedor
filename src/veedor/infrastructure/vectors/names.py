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
        f"SELECT buyer_ruc, any_value(buyer_name) AS buyer_name FROM {table} "
        f"WHERE buyer_ruc IN ({placeholders}) AND buyer_name IS NOT NULL GROUP BY buyer_ruc"
    )
    try:
        rows = lake.fetch(sql, list(rucs), tables=(table,))
    except LakeUnavailableError:
        logger.warning("Lake unavailable: buyer names omitted from similar-process results")
        return {}
    return {row["buyer_ruc"]: row["buyer_name"] for row in rows}


def lake_buyer_names(rucs: Sequence[str]) -> Mapping[str, str]:
    """Process-wide cached lookup used by `find_similar` when no lookup is injected."""
    missing = [ruc for ruc in rucs if ruc not in _CACHE]
    if missing:
        settings = get_settings()
        if len(_CACHE) > _MAX_CACHE:
            _CACHE.clear()
        _CACHE.update(buyer_names_from(LakeReader(settings.lake_dir, settings.marts_dir), missing))
    return {ruc: _CACHE[ruc] for ruc in rucs if ruc in _CACHE}
