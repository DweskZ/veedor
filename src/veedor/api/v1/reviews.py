from __future__ import annotations

from fastapi import APIRouter, Depends, status

from veedor.api.deps import Policy, Reviews, authorize_review_write
from veedor.api.params import OcidPath
from veedor.api.security import limit_review_writes
from veedor.api.v1._responses import NOT_FOUND, UNAVAILABLE
from veedor.schemas.common import ErrorResponse
from veedor.schemas.reviews import ReviewCreate, ReviewOut

router = APIRouter(prefix="/processes/{ocid}/reviews", tags=["revisiones"])

_WRITE_ERRORS = {
    401: {"model": ErrorResponse, "description": "Token ausente o incorrecto."},
    403: {"model": ErrorResponse, "description": "Las revisiones están deshabilitadas."},
    422: {"model": ErrorResponse, "description": "Entrada inválida o redacción que afirma una falta."},
    429: {"model": ErrorResponse, "description": "Límite de solicitudes."},
}


@router.post(
    "",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    # Authenticate first, then rate-limit: anonymous clients cannot exhaust the bucket.
    dependencies=[Depends(authorize_review_write), Depends(limit_review_writes)],
    responses={**_WRITE_ERRORS, **NOT_FOUND, **UNAVAILABLE},
    summary="Registrar una revisión humana",
)
def create_review(ocid: OcidPath, body: ReviewCreate, service: Reviews) -> ReviewOut:
    """Requiere `VEEDOR_REVIEWS_ENABLED=true` y `Authorization: Bearer <VEEDOR_REVIEWS_TOKEN>`."""
    record = service.submit(ocid, body.status.value, body.note, body.reviewer)
    return ReviewOut.model_validate(record)


@router.get("", response_model=list[ReviewOut], responses=UNAVAILABLE, summary="Historial de revisiones")
def list_reviews(ocid: OcidPath, service: Reviews, policy: Policy) -> list[ReviewOut]:
    """Lista vacía mientras las revisiones estén deshabilitadas."""
    if not policy.enabled:
        return []
    return [ReviewOut.model_validate(record) for record in service.history(ocid)]
