from __future__ import annotations

from fastapi import APIRouter

from veedor.api.deps import Lake
from veedor.api.params import RucPath
from veedor.api.v1._responses import NOT_FOUND, UNAVAILABLE
from veedor.schemas.suppliers import SupplierDetail
from veedor.use_cases.queries import suppliers as use_case

router = APIRouter(prefix="/suppliers", tags=["proveedores"])


@router.get(
    "/{ruc}",
    response_model=SupplierDetail,
    responses={**NOT_FOUND, **UNAVAILABLE},
    summary="Perfil de proveedor",
)
def get_supplier(ruc: RucPath, lake: Lake) -> dict:
    """Perfil agregado, datos de registros públicos y procesos recientes. Personas naturales se enmascaran."""
    return use_case.get_supplier(lake, ruc)
