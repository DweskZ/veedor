"""Processes whose purchased object is closest to a given process (pgvector)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from veedor.api.deps import Lake
from veedor.api.params import OcidPath
from veedor.api.v1._responses import NOT_FOUND, UNAVAILABLE
from veedor.infrastructure.db.session import get_session
from veedor.infrastructure.vectors.names import buyer_names_from
from veedor.infrastructure.vectors.repository import PgVectorStore
from veedor.schemas.similar import SimilarProcessesOut, SimilarProcessOut
from veedor.use_cases.queries.processes import process_exists
from veedor.use_cases.similar_processes import (
    MAX_K,
    ProcessNotIndexed,
    VectorStore,
    VectorsUnavailable,
    find_similar,
)

router = APIRouter(prefix="/processes", tags=["procesos"])

KQuery = Annotated[int, Query(ge=1, le=MAX_K, description="Cantidad de procesos similares (1 a 50).")]
SameBuyerQuery = Annotated[bool, Query(description="Solo procesos de la misma entidad contratante.")]


def get_vector_store(session: Annotated[Session, Depends(get_session)]) -> VectorStore:
    return PgVectorStore(session)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@router.get(
    "/{ocid}/similar",
    response_model=SimilarProcessesOut,
    responses={**NOT_FOUND, **UNAVAILABLE},
    summary="Procesos similares por objeto de compra",
)
def similar_processes(
    ocid: OcidPath,
    lake: Lake,
    store: Annotated[VectorStore, Depends(get_vector_store)],
    k: KQuery = 10,
    same_buyer: SameBuyerQuery = False,
) -> SimilarProcessesOut | JSONResponse:
    """Vecinos más cercanos en el índice vectorial. Responde 404 si el proceso no existe o no está
    indexado (compras de catálogo o sin texto) y 503 si el índice no está disponible."""

    def names(rucs: Sequence[str]) -> Mapping[str, str]:
        return buyer_names_from(lake, rucs)

    try:
        found = find_similar(ocid, k, same_buyer, store=store, buyer_names=names)
    except VectorsUnavailable:
        return _error(503, "vectors_unavailable", "El índice de procesos similares no está disponible.")
    except ProcessNotIndexed:
        if not process_exists(lake, ocid):
            return _error(404, "not_found", "No se encontró el recurso solicitado.")
        return _error(
            404,
            "not_indexed",
            "El proceso no está en el índice de similitud (compra de catálogo o sin texto).",
        )
    items = [SimilarProcessOut.model_validate(asdict(item)) for item in found]
    return SimilarProcessesOut(ocid=ocid, k=k, same_buyer=same_buyer, items=items)
