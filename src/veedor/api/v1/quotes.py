"""`GET /processes/{ocid}/quotes`: verbatim quotes from the process's own published text."""

from __future__ import annotations

from fastapi import APIRouter

from veedor.api.deps import Lake
from veedor.api.params import OcidPath
from veedor.api.v1._responses import NOT_FOUND, UNAVAILABLE
from veedor.schemas.quotes import ProcessQuotes
from veedor.use_cases.queries import quotes as use_case

router = APIRouter(prefix="/processes", tags=["procesos"])


@router.get(
    "/{ocid}/quotes",
    response_model=ProcessQuotes,
    responses={**NOT_FOUND, **UNAVAILABLE},
    summary="Citas del texto publicado del proceso",
)
def get_process_quotes(ocid: OcidPath, lake: Lake) -> dict:
    """Hasta tres citas textuales de las preguntas, respuestas y textos de adjudicación que el propio
    proceso publicó, elegidas por su cercanía de significado con las señales activadas. Son palabras de
    oferentes o de la entidad, no de Veedor. 404 si el proceso no existe; 200 con lista vacía si no hay
    citas. Cada cita se vuelve a revisar aquí y se descarta si ya no es segura."""
    return use_case.get_process_quotes(lake, ocid)
