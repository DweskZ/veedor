"""`GET /processes/{ocid}/investigation`: stored investigations only.

Never starts a run, never calls a tool or a language model: investigations are produced by the CLI.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from veedor.api.deps import Lake
from veedor.api.params import OcidPath
from veedor.api.v1._responses import NOT_FOUND, UNAVAILABLE
from veedor.core.settings import get_settings
from veedor.domain.masking import mask_payload
from veedor.infrastructure.investigations.store import InvestigationStore
from veedor.schemas.investigation import InvestigationOut
from veedor.use_cases.investigate import read_investigation
from veedor.use_cases.queries.ports import NotFoundError
from veedor.use_cases.queries.processes import name_context

router = APIRouter(prefix="/processes", tags=["procesos"])


@lru_cache
def get_investigation_store() -> InvestigationStore:
    return InvestigationStore(get_settings().data_dir / "investigations")


Store = Annotated[InvestigationStore, Depends(get_investigation_store)]


@router.get(
    "/{ocid}/investigation",
    response_model=InvestigationOut,
    responses={**NOT_FOUND, **UNAVAILABLE},
    summary="Investigación almacenada de un proceso",
)
def get_investigation(ocid: OcidPath, lake: Lake, store: Store) -> dict:
    """Resultado de una investigación ya realizada por la línea de comandos; 404 si no existe."""
    record = read_investigation(store, ocid)
    if record is None:
        raise NotFoundError("investigation", ocid)
    persons, protected = name_context(lake, ocid)
    return mask_payload(record.model_dump(mode="json", exclude={"facts"}), persons, protected)
