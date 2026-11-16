from __future__ import annotations

from fastapi import APIRouter

from veedor.api.deps import Lake
from veedor.api.v1._responses import UNAVAILABLE
from veedor.schemas.stats import Stats
from veedor.use_cases.queries import stats as use_case

router = APIRouter(tags=["resumen"])


@router.get("/stats", response_model=Stats, responses=UNAVAILABLE, summary="Resumen general")
def get_stats(lake: Lake) -> dict:
    """Totales, cobertura, distribución de puntajes y conteo de señales por código."""
    stats = use_case.get_stats_cached(lake)
    stats["available_tables"] = lake.availability()
    return stats
