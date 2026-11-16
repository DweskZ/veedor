from __future__ import annotations

from fastapi import APIRouter, Depends

from veedor.api.deps import Lake, Paging
from veedor.api.params import (
    BuyerRucQuery,
    MethodQuery,
    MinScoreQuery,
    OcidPath,
    QueryText,
    RegionQuery,
    SignalCode,
    SortQuery,
    WithSignalsQuery,
    YearQuery,
)
from veedor.api.security import limit_dossier_builds
from veedor.api.v1._responses import NOT_FOUND, UNAVAILABLE
from veedor.schemas.common import ErrorResponse, Page
from veedor.schemas.context import ProcessContext
from veedor.schemas.dossier import DossierOut
from veedor.schemas.processes import ProcessDetail, ProcessSummary
from veedor.use_cases.queries import dossier as dossier_use_case
from veedor.use_cases.queries import process_context, random_process
from veedor.use_cases.queries import processes as use_case
from veedor.use_cases.queries.processes import DEFAULT_SORT, ProcessFilters

router = APIRouter(prefix="/processes", tags=["procesos"])


@router.get(
    "",
    response_model=Page[ProcessSummary],
    responses=UNAVAILABLE,
    summary="Listar procesos con su puntaje de riesgo",
)
def list_processes(
    lake: Lake,
    paging: Paging,
    year: YearQuery = None,
    method: MethodQuery = None,
    buyer_ruc: BuyerRucQuery = None,
    signal: SignalCode | None = None,
    min_score: MinScoreQuery = None,
    q: QueryText = None,
    sort: SortQuery = DEFAULT_SORT,
    region: RegionQuery = None,
) -> dict:
    filters = ProcessFilters(
        year=year,
        method=method,
        buyer_ruc=buyer_ruc,
        signal=signal.value if signal else None,
        min_score=min_score,
        q=q,
        region=region.value if region else None,
    )
    return use_case.list_processes(lake, filters, page=paging.page, page_size=paging.page_size, sort=sort)


@router.get(
    "/random",
    response_model=ProcessSummary,
    responses={**NOT_FOUND, **UNAVAILABLE},
    summary="Un proceso al azar",
)
def get_random_process(
    lake: Lake, with_signals: WithSignalsQuery = None, min_score: MinScoreQuery = None
) -> dict:
    """Un proceso elegido con la misma probabilidad entre los que cumplen el filtro, con el mismo
    formato que un elemento de la lista. Solo procesos que la API puede abrir y cuyo adjudicatario es
    una empresa o una entidad pública. Nunca se cachea; 404 si ningún proceso cumple el filtro."""
    return random_process.pick_random_process(lake, with_signals=with_signals, min_score=min_score)


@router.get(
    "/{ocid}",
    response_model=ProcessDetail,
    responses={**NOT_FOUND, **UNAVAILABLE},
    summary="Detalle de un proceso",
)
def get_process(ocid: OcidPath, lake: Lake) -> dict:
    """Hechos del proceso, señales activadas con su evidencia y perfil del adjudicatario."""
    return use_case.get_process(lake, ocid)


@router.get(
    "/{ocid}/context",
    response_model=ProcessContext,
    responses={**NOT_FOUND, **UNAVAILABLE},
    summary="Dónde se ubica el proceso entre los de su mismo método y año",
)
def get_process_context(ocid: OcidPath, lake: Lake) -> dict:
    """Distribución del número de oferentes, mediana y cuartiles de la relación adjudicación/presupuesto
    y de la ventana de ofertas en días, para el método y el año del proceso, y la posición de este
    proceso en cada una (valor y percentil). Los datos que el procedimiento no publica son nulos con
    su motivo. No contiene interpretaciones ni datos personales."""
    return process_context.get_process_context(lake, ocid)


@router.get(
    "/{ocid}/dossier",
    response_model=DossierOut,
    dependencies=[Depends(limit_dossier_builds)],
    responses={
        **NOT_FOUND,
        **UNAVAILABLE,
        429: {"model": ErrorResponse, "description": "Límite de solicitudes."},
    },
    summary="Expediente de evidencia",
)
def get_dossier(ocid: OcidPath, lake: Lake) -> dict:
    """Expediente generado en modo plantilla (o LLM verificado) con trazabilidad a los datos."""
    return dossier_use_case.get_dossier(lake, ocid)
