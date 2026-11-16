from __future__ import annotations

from fastapi import APIRouter

from veedor.api.deps import Lake
from veedor.api.v1._responses import UNAVAILABLE
from veedor.schemas.stats import RegionStats, Stats, YearStats
from veedor.use_cases.queries import region_stats, year_stats
from veedor.use_cases.queries import stats as use_case

router = APIRouter(tags=["resumen"])


@router.get("/stats", response_model=Stats, responses=UNAVAILABLE, summary="Resumen general")
def get_stats(lake: Lake) -> dict:
    """Totales, cobertura, distribución de puntajes y conteo de señales por código."""
    stats = use_case.get_stats_cached(lake)
    stats["available_tables"] = lake.availability()
    return stats


@router.get(
    "/stats/by-region",
    response_model=RegionStats,
    responses=UNAVAILABLE,
    summary="Procesos competitivos y señales por provincia de la entidad contratante",
)
def get_stats_by_region(lake: Lake) -> dict:
    """Una fila por provincia de la **entidad contratante** (no del lugar de ejecución). Los
    porcentajes se calculan sobre los procesos competitivos; las provincias con menos de 500 se
    marcan `small_sample`. Más señales no implican más problemas: son indicadores, no acusaciones."""
    return region_stats.get_region_stats(lake)


@router.get(
    "/stats/by-year",
    response_model=YearStats,
    responses=UNAVAILABLE,
    summary="Evolución anual: oferente único, señales y mezcla de métodos",
)
def get_stats_by_year(lake: Lake) -> dict:
    """Por año: procesos, porcentaje de subastas inversas electrónicas con un solo oferente (el único
    procedimiento con nombre estable en todo el periodo), porcentaje de procesos competitivos con
    señal y participación de cada grupo de métodos en el monto adjudicado. Incluye aclaraciones."""
    return year_stats.get_year_stats(lake)
