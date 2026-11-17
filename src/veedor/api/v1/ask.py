"""`POST /processes/{ocid}/ask`: the only route that may reach a language model.

Off by default (`VEEDOR_ASK_ENABLED`): 404 when disabled, identical to an unknown route. Per-IP rate
limits (strict while a model can be called, generous for retrieval-only answers, which cost nothing)
and a daily budget bound the cost; with no key, or the budget spent, it answers by retrieval only.
The question is untrusted: never logged, stored or put in a span (docs/SECURITY.md, "Question answering").
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from veedor.api.ask_wiring import get_ask_service, usage_store
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
from veedor.use_cases.ask import AskService, InvalidQuestionError, UsageStore
from veedor.use_cases.queries.ports import NotFoundError
from veedor.use_cases.queries.processes import name_context

router = APIRouter(prefix="/processes", tags=["procesos"])
logger = logging.getLogger(__name__)

_PROBLEM_MESSAGES = {
    Problem.TOO_SHORT: "La pregunta es demasiado corta (mínimo 3 caracteres).",
    Problem.TOO_LONG: "La pregunta es demasiado larga (máximo 300 caracteres).",
    Problem.CONTROL_CHARACTERS: "La pregunta contiene saltos de línea o caracteres de control.",
    Problem.NO_LETTERS: "La pregunta debe contener palabras.",
    Problem.SEVERAL_QUESTIONS: "Haga una sola pregunta por vez.",
}


class AskLimits:
    """Per-client-IP limits (one instance per kind of answer: `model` strict, `retrieval` generous).

    In memory (the default): sliding windows counted per worker process and reset on restart, so the effective
    limit is multiplied by the number of workers. With `VEEDOR_ASK_USAGE_SHARED` the counts live in the
    database (fixed one-minute and one-hour buckets per client hash): one count for every worker, kept across
    restarts. If the database fails the in-memory windows apply for that request."""

    def __init__(
        self, per_minute: int, per_hour: int, store: UsageStore | None = None, kind: str = "model"
    ) -> None:
        self.minute = SlidingWindowRateLimiter(per_minute, 60.0)
        self.hour = SlidingWindowRateLimiter(per_hour, 3600.0)
        self._store = store
        self._prefix = "" if kind == "model" else f"{kind}:"  # the model pair keeps its earlier bucket names

    def allow(self, client: str) -> bool:
        if self._store is not None:
            try:
                return self._allow_shared(client)
            except Exception:  # noqa: BLE001 - a database problem must not switch the limit off
                logger.warning("shared ask limits unavailable; counting in memory for this worker")
        return self.minute.allow(client) and self.hour.allow(client)

    def _allow_shared(self, client: str) -> bool:
        assert self._store is not None
        who = hashlib.sha256(client.encode()).hexdigest()[:16]
        now = int(time.time())
        p = self._prefix
        return self._store.consume(f"{p}m:{who}:{now // 60}", self.minute.limit) and self._store.consume(
            f"{p}h:{who}:{now // 3600}", self.hour.limit
        )

    def retry_after(self, client: str) -> int:
        """Seconds until the client may ask again: the longer wait of the two windows that are full."""
        if self._store is not None:
            try:
                return self._retry_after_shared(client)
            except Exception:  # noqa: BLE001
                pass
        waits = [
            limiter.retry_after(client) for limiter in (self.minute, self.hour) if limiter.is_full(client)
        ]
        return max(waits or [1])

    def _retry_after_shared(self, client: str) -> int:
        assert self._store is not None
        who = hashlib.sha256(client.encode()).hexdigest()[:16]
        now = int(time.time())
        waits = []
        for prefix, size, limit in (("m", 60, self.minute.limit), ("h", 3600, self.hour.limit)):
            if self._store.used(f"{self._prefix}{prefix}:{who}:{now // size}") >= limit:
                waits.append(size - now % size)
        return max(waits or [1])


_limits: dict[str, AskLimits] | None = {}  # reset to None by the tests


def get_ask_limits(*, model_mode: bool = True) -> AskLimits:
    """Strict limits while a model can be called (it costs money), generous ones for retrieval only."""
    global _limits
    if _limits is None:
        _limits = {}
    settings = get_settings()
    kind = "model" if model_mode else "retrieval"
    wanted = (
        (settings.ask_rate_per_minute, settings.ask_rate_per_hour)
        if model_mode
        else (settings.ask_retrieval_rate_per_minute, settings.ask_retrieval_rate_per_hour)
    )
    current = _limits.get(kind)
    if current is None or (current.minute.limit, current.hour.limit) != wanted:
        _limits[kind] = current = AskLimits(*wanted, usage_store(settings), kind)
    return current


def model_may_be_called(service: AskService) -> bool:
    """True when this service can spend model budget: a model is set and the daily budget is not zero."""
    return service.selector is not None and (service.budget is None or service.budget.limit > 0)


def require_ask_enabled() -> None:
    """First dependency: a disabled route is a plain 404, before any validation of the request."""
    if not get_settings().ask_enabled:
        raise NotFoundError("route", "ask")


def limit_questions(request: Request, service: Annotated[AskService, Depends(get_ask_service)]) -> None:
    client = request.client.host if request.client else "unknown"
    limits = get_ask_limits(model_mode=model_may_be_called(service))
    if not limits.allow(client):
        raise HTTPException(
            status_code=429,
            detail="Demasiadas preguntas recientes. Intente más tarde.",
            headers={"Retry-After": str(limits.retry_after(client))},
        )


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
