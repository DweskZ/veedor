"""`GET /processes/{ocid}/provenance`: source, exact field and verification path of every fact shown."""

from __future__ import annotations

from fastapi import APIRouter

from veedor.api.deps import Lake
from veedor.api.params import OcidPath
from veedor.api.v1._responses import NOT_FOUND, UNAVAILABLE
from veedor.api.v1.investigations import Store
from veedor.schemas.provenance import ProcessProvenance
from veedor.use_cases.investigate import read_investigation
from veedor.use_cases.queries import provenance as use_case

router = APIRouter(prefix="/processes", tags=["procesos"])


@router.get(
    "/{ocid}/provenance",
    response_model=ProcessProvenance,
    responses={**NOT_FOUND, **UNAVAILABLE},
    summary="De dónde sale cada dato del proceso",
)
def get_process_provenance(ocid: OcidPath, lake: Lake, store: Store) -> dict:
    """Fuentes (con licencia y fecha de obtención) y, para cada dato de la página del proceso, el campo
    exacto de origen, si es un valor calculado (con su fórmula en español) y cómo verificarlo. Los valores
    siguen las mismas reglas de enmascaramiento que el detalle del proceso."""
    return use_case.get_process_provenance(lake, ocid, read_investigation(store, ocid))
