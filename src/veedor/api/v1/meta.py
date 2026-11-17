from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from veedor.api.deps import Policy
from veedor.api.meta import VERSION
from veedor.core.settings import get_settings

router = APIRouter(tags=["health"])


class Meta(BaseModel):
    version: str
    reviews_enabled: bool = Field(description="True when reviews can be written (flag on, token set).")
    ask_enabled: bool = Field(default=False, description="True when the question route is switched on.")
    quotes_enabled: bool = Field(
        default=False, description="True when verbatim quotes are served (off by default, docs/QUOTES.md)."
    )
    ask_mode: str | None = Field(
        default=None,
        description="model | retrieval when the route is on (retrieval without a model); null if off.",
    )


@router.get("/meta", response_model=Meta, summary="Capacidades del servicio")
def get_meta(policy: Policy) -> Meta:
    """Permite a la web ocultar el formulario de revisión cuando está deshabilitado."""
    settings = get_settings()
    model = settings.model_configured and settings.ask_daily_budget > 0
    mode = ("model" if model else "retrieval") if settings.ask_enabled else None
    return Meta(
        version=VERSION, reviews_enabled=policy.can_write, ask_enabled=settings.ask_enabled,
        quotes_enabled=settings.quotes_enabled, ask_mode=mode
    )
