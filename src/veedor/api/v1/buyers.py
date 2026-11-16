from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError

from veedor.api.deps import Lake
from veedor.api.params import BuyerSearchLimit, RucPath
from veedor.api.v1._responses import NOT_FOUND, UNAVAILABLE
from veedor.domain.text_match import has_control_characters
from veedor.schemas.buyers import BuyerDetail, BuyerSearchResult
from veedor.use_cases.queries import buyer_search
from veedor.use_cases.queries import buyers as use_case

router = APIRouter(prefix="/buyers", tags=["entidades"])

MIN_SEARCH_LENGTH, MAX_SEARCH_LENGTH = 3, 60


def get_search_text(
    q: str = Query(
        description="Texto del nombre de la entidad (3 a 60 caracteres sin contar espacios de los extremos).",
        max_length=4 * MAX_SEARCH_LENGTH,
        examples=["municip"],
    ),
) -> str:
    """Trim, then require 3-60 characters and no control characters; otherwise 422."""
    text = q.strip()
    if not MIN_SEARCH_LENGTH <= len(text) <= MAX_SEARCH_LENGTH or has_control_characters(text):
        raise RequestValidationError(
            [
                {
                    "loc": ("query", "q"),
                    "msg": f"q must have {MIN_SEARCH_LENGTH} to {MAX_SEARCH_LENGTH} characters, "
                    "without control characters",
                    "type": "value_error",
                }
            ]
        )
    return text


@router.get(
    "/search",
    response_model=BuyerSearchResult,
    responses=UNAVAILABLE,
    summary="Buscar entidades contratantes por nombre",
)
def search_buyers(lake: Lake, text: str = Depends(get_search_text), limit: BuyerSearchLimit = 10) -> dict:
    """Hasta 10 entidades cuyo nombre coincide con el texto, sin distinguir mayúsculas ni tildes.
    Primero las que empiezan con el texto y las que lo tienen al inicio de una palabra. No incluye
    personas naturales."""
    return buyer_search.search_buyers(lake, text, limit)


@router.get(
    "/{ruc}",
    response_model=BuyerDetail,
    responses={**NOT_FOUND, **UNAVAILABLE},
    summary="Resumen de entidad contratante",
)
def get_buyer(ruc: RucPath, lake: Lake) -> dict:
    """Resumen de la entidad, principales proveedores y mezcla de señales."""
    return use_case.get_buyer(lake, ruc)
