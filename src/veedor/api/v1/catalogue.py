from __future__ import annotations

from fastapi import APIRouter

from veedor.schemas.signals import SignalInfo
from veedor.use_cases.queries.catalogue import list_signal_catalogue

router = APIRouter(prefix="/signals", tags=["señales"])


@router.get("", response_model=list[SignalInfo], summary="Catálogo de señales de riesgo")
def get_signals() -> list[dict]:
    """Código, etiqueta, descripción y regla de umbral de cada indicador."""
    return list_signal_catalogue()
