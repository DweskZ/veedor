"""Consistent error model: every error is `{"error": {"code", "message", "details"?}}`."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from veedor.infrastructure.glossary import GlossaryUnavailableError
from veedor.use_cases.queries.ports import DossierUnavailableError, LakeUnavailableError, NotFoundError
from veedor.use_cases.queries.processes import InvalidSortError
from veedor.use_cases.reviews import (
    ForbiddenWordingError,
    ReviewAuthError,
    ReviewsDisabledError,
    ReviewStoreUnavailableError,
)

logger = logging.getLogger(__name__)


def _response(status: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    body: dict = {"code": code, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(LakeUnavailableError)
    async def _lake(_: Request, exc: LakeUnavailableError) -> JSONResponse:
        return _response(
            503,
            "data_unavailable",
            f"Los datos requeridos aún no están disponibles: {', '.join(exc.tables)}.",
        )

    @app.exception_handler(ReviewStoreUnavailableError)
    async def _store(_: Request, exc: ReviewStoreUnavailableError) -> JSONResponse:
        return _response(
            503, "review_store_unavailable", f"El almacén de revisiones no está disponible. {exc}"
        )

    @app.exception_handler(DossierUnavailableError)
    async def _dossier(_: Request, exc: DossierUnavailableError) -> JSONResponse:
        return _response(
            503, "dossier_unavailable", "El generador de expedientes no está disponible todavía."
        )

    @app.exception_handler(GlossaryUnavailableError)
    async def _glossary(_: Request, exc: GlossaryUnavailableError) -> JSONResponse:
        logger.warning("Glossary unavailable: %s", exc)
        return _response(503, "glossary_unavailable", "El glosario no está disponible por ahora.")

    @app.exception_handler(ReviewsDisabledError)
    async def _disabled(_: Request, exc: ReviewsDisabledError) -> JSONResponse:
        return _response(403, "reviews_disabled", "Las revisiones están deshabilitadas en este servidor.")

    @app.exception_handler(ReviewAuthError)
    async def _auth(_: Request, exc: ReviewAuthError) -> JSONResponse:
        response = _response(401, "invalid_token", "Token ausente o incorrecto.")
        response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.exception_handler(ForbiddenWordingError)
    async def _wording(_: Request, exc: ForbiddenWordingError) -> JSONResponse:
        return _response(
            422,
            "forbidden_wording",
            "El texto afirma una falta o un delito (" + ", ".join(exc.terms) + "). Veedor solo registra "
            "señales de riesgo: reformule usando 'señal de riesgo', 'indicador' o 'atípico'.",
        )

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return _response(404, "not_found", "No se encontró el recurso solicitado.")

    @app.exception_handler(InvalidSortError)
    async def _sort(_: Request, exc: InvalidSortError) -> JSONResponse:
        return _response(422, "invalid_sort", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": [str(part) for part in err["loc"]], "msg": err["msg"], "type": err["type"]}
            for err in exc.errors()
        ]
        return _response(422, "validation_error", "La solicitud no es válida.", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        response = _response(exc.status_code, "http_error", str(exc.detail))
        if exc.status_code == 429 and exc.headers and "Retry-After" in exc.headers:
            response.headers["Retry-After"] = exc.headers["Retry-After"]
        return response

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return _response(500, "internal_error", "Error interno del servidor.")
