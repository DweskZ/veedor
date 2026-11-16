from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from veedor.api.deps import Policy
from veedor.api.meta import VERSION

router = APIRouter(tags=["health"])


class Meta(BaseModel):
    version: str
    reviews_enabled: bool = Field(description="True when reviews can be written (flag on and token set).")


@router.get("/meta", response_model=Meta, summary="Capacidades del servicio")
def get_meta(policy: Policy) -> Meta:
    """Permite a la web ocultar el formulario de revisión cuando está deshabilitado."""
    return Meta(version=VERSION, reviews_enabled=policy.can_write)
