from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from veedor.api.deps import Lake
from veedor.api.meta import VERSION

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str
    version: str
    tables: dict[str, bool]


@router.get("/health", response_model=Health, summary="Estado del servicio")
def health(lake: Lake) -> Health:
    """Liveness plus which Parquet tables are present on disk."""
    return Health(status="ok", version=VERSION, tables=lake.availability())
