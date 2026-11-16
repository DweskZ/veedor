"""`POST /processes/{ocid}/ask`: the only route that may reach a language model.

Off by default (`VEEDOR_ASK_ENABLED`): 404 when disabled, identical to an unknown route. Per-IP rate
limits and a daily budget bound the cost; with no key, or the budget spent, it answers by retrieval only.
The question is untrusted: never logged, stored or put in a span (docs/SECURITY.md, "Question answering").
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from veedor.api.ask_wiring import get_ask_service
from veedor.api.deps import Lake
from veedor.api.params import OcidPath
from veedor.api.security import SlidingWindowRateLimiter
from veedor.api.v1._responses import NOT_FOUND, UNAVAILABLE
from veedor.core.settings import get_settings
from veedor.domain.masking import mask_payload
from veedor.domain.qa.screen import Problem
from veedor.infrastructure.telemetry import span
from veedor.schemas.ask import AskRequest, AskResponse
from veedor.schemas.common import ErrorResponse
from veedor.use_cases.ask import AskService, InvalidQuestionError
from veedor.use_cases.queries.ports import NotFoundError
from veedor.use_cases.queries.processes import name_context

router = APIRouter(prefix="/processes", tags=["procesos"])

_PROBLEM_MESSAGES = {
    Problem.TOO_SHORT: "La pregunta es demasiado corta (mínimo 3 caracteres).",
    Problem.TOO_LONG: "La pregunta es demasiado larga (máximo 300 caracteres).",
    Problem.CONTROL_CHARACTERS: "La pregunta contiene saltos de línea o caracteres de control.",
    Problem.NO_LETTERS: "La pregunta debe contener palabras.",
    Problem.SEVERAL_QUESTIONS: "Haga una sola pregunta por vez.",
}


class AskLimits:
    """Per-client-IP limits, counted per worker process (the effective limit is multiplied by the workers)."""

    def __init__(self, per_minute: int, per_hour: int) -> None:
        self.minute = SlidingWindowRateLimiter(per_minute, 60.0)
        self.hour = SlidingWindowRateLimiter(per_hour, 3600.0)

    def allow(self, client: str) -> bool:
        return self.minute.allow(client) and self.hour.allow(client)


_limits: AskLimits | None = None


def get_ask_limits() -> AskLimits:
    global _limits
    settings = get_settings()
    if _limits is None or (_limits.minute.limit, _limits.hour.limit) != (
        settings.ask_rate_per_minute,
        settings.ask_rate_per_hour,
    ):
        _limits = AskLimits(settings.ask_rate_per_minute, settings.ask_rate_per_hour)
    return _limits


def require_ask_enabled() -> None:
    """First dependency: a disabled route is a plain 404, before any validation of the request."""
    if not get_settings().ask_enabled:
        raise NotFoundError("route", "ask")


def limit_questions(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    if not get_ask_limits().allow(client):
        raise HTTPException(status_code=429, detail="Demasiadas preguntas recientes. Intente más tarde.")


@router.post(
    "/{ocid}/ask",
    response_model=AskResponse,
    dependencies=[Depends(require_ask_enabled), Depends(limit_questions)],
    responses={
        **NOT_FOUND,
        **UNAVAILABLE,
        422: {"model": ErrorResponse, "description": "La pregunta no es válida."},
        429: {"model": ErrorResponse, "description": "Límite de preguntas."},
    },
    summary="Pregunta sobre un proceso",
)
def ask_process(
    ocid: OcidPath,
    body: AskRequest,
    lake: Lake,
    service: Annotated[AskService, Depends(get_ask_service)],
) -> dict:
    """Responde con frases escritas por el sistema a partir de los hechos almacenados de este proceso,
    cada una con su fuente, y con citas textuales atribuidas. Un modelo, cuando hay uno, solo elige
    identificadores de hechos; no escribe texto y no ve las citas. Veedor describe registros y no emite
    juicios. La pregunta no se guarda ni se registra."""
    with span("ask", ocid=ocid) as handle:
        try:
            answer = service.ask(ocid, body.question)
        except InvalidQuestionError as exc:
            raise HTTPException(status_code=422, detail=_PROBLEM_MESSAGES[exc.problem]) from None
        handle.set_attributes(
            mode=answer.mode,
            outcome=answer.reason.value,
            passed=bool(answer.grounded),
            prompt_tokens=answer.prompt_tokens,
            completion_tokens=answer.completion_tokens,
            n_findings=len(answer.sentences),
        )
    persons, protected = name_context(lake, ocid)
    payload = {
        "ocid": answer.ocid,
        "answerable": answer.answerable,
        "mode": answer.mode,
        "reason": answer.reason.value,
        "sentences": [
            {"text": s.text, "fact_id": s.fact_id, "source_id": s.source_id, "source_field": s.source_field}
            for s in answer.sentences
        ],
        "quotes": [
            {
                "quote_id": q.quote_id, "text": q.text, "kind": q.kind, "date": q.date,
                "source_field": q.source_field, "truncated": q.truncated,
            }
            for q in answer.quotes
        ],
        "note_es": answer.note_es,
    }  # fmt: skip
    return mask_payload(payload, persons, protected)
