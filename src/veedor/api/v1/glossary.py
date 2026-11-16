from __future__ import annotations

from fastapi import APIRouter

from veedor.api.deps import GlossaryDep
from veedor.api.v1._responses import UNAVAILABLE
from veedor.schemas.glossary import Glossary

router = APIRouter(tags=["glosario"])


@router.get(
    "/glossary",
    response_model=Glossary,
    responses=UNAVAILABLE,
    summary="Glosario de términos de contratación pública",
)
def get_glossary(store: GlossaryDep) -> dict:
    """Términos, sinónimos y definiciones en español claro, de un único archivo del repositorio.
    Responde 503 `glossary_unavailable` si el archivo falta o no tiene el formato esperado."""
    return {"items": store.items()}
