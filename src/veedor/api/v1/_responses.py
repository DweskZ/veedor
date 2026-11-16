"""Reusable OpenAPI error responses."""

from __future__ import annotations

from typing import Any

from veedor.schemas.common import ErrorResponse

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "No existe en los datos."}
}
UNAVAILABLE: dict[int | str, dict[str, Any]] = {
    503: {"model": ErrorResponse, "description": "Datos o servicio dependiente no disponible."}
}
