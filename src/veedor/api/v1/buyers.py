from __future__ import annotations

from fastapi import APIRouter

from veedor.api.deps import Lake
from veedor.api.params import RucPath
from veedor.api.v1._responses import NOT_FOUND, UNAVAILABLE
from veedor.schemas.buyers import BuyerDetail
from veedor.use_cases.queries import buyers as use_case

router = APIRouter(prefix="/buyers", tags=["entidades"])


@router.get(
    "/{ruc}",
    response_model=BuyerDetail,
    responses={**NOT_FOUND, **UNAVAILABLE},
    summary="Resumen de entidad contratante",
)
def get_buyer(ruc: RucPath, lake: Lake) -> dict:
    """Resumen de la entidad, principales proveedores y mezcla de señales."""
    return use_case.get_buyer(lake, ruc)
