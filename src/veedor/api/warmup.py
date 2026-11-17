"""Fill the in-memory aggregate caches when a worker starts, off the request path.

Each uvicorn worker keeps its own caches. Without this, the first `/stats/by-year` and `/stats/by-region`
request of every worker pays the full DuckDB aggregate (about 200 ms and 170 ms) and, with two workers,
the cost is paid twice. A failure here is harmless: the request that needs the value computes it as before.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def warm_aggregates() -> None:
    from veedor.api.deps import get_reader
    from veedor.use_cases.queries import region_stats, stats, thresholds, year_stats

    try:
        reader = get_reader()
        if not reader.has_table("processes"):
            return
        for compute in (
            stats.get_stats_cached,
            year_stats.get_year_stats,
            region_stats.get_region_stats,
            thresholds.get_threshold_stats,
        ):
            try:
                compute(reader)
            except Exception as exc:  # noqa: BLE001 - optional marts may be absent
                logger.info("Cache warm-up skipped %s: %s", compute.__module__, exc.__class__.__name__)
    except Exception as exc:  # noqa: BLE001
        logger.info("Cache warm-up failed: %s", exc.__class__.__name__)


@asynccontextmanager
async def warm_caches_on_start(_: FastAPI) -> AsyncIterator[None]:
    threading.Thread(target=warm_aggregates, name="cache-warmup", daemon=True).start()
    yield
