"""Edge validation for path and query parameters (strict patterns, bounded lengths)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from fastapi import Path, Query

from veedor.domain.signals import SIGNALS_BY_CODE

OCID_PATTERN = r"^ocds-5wno2w-[A-Za-z0-9._\-]{1,120}$"
RUC_PATTERN = r"^[0-9]{13}$"
METHOD_PATTERN = r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ .,()/\-]{1,120}$"
SORT_PATTERN = r"^[+-]?[a-z_]{1,30}$"
MIN_YEAR, MAX_YEAR = 2000, 2100
MAX_QUERY_LENGTH = 80

SignalCode = StrEnum("SignalCode", {code: code for code in SIGNALS_BY_CODE})

OcidPath = Annotated[str, Path(pattern=OCID_PATTERN, description="Identificador OCDS del proceso.")]
RucPath = Annotated[str, Path(pattern=RUC_PATTERN, description="RUC de 13 dígitos.")]

YearQuery = Annotated[int | None, Query(ge=MIN_YEAR, le=MAX_YEAR)]
MethodQuery = Annotated[str | None, Query(pattern=METHOD_PATTERN, description="Método de contratación.")]
BuyerRucQuery = Annotated[str | None, Query(pattern=RUC_PATTERN)]
MinScoreQuery = Annotated[float | None, Query(ge=0, le=100)]
QueryText = Annotated[
    str | None,
    Query(min_length=1, max_length=MAX_QUERY_LENGTH, description="Texto en código, entidad o descripción."),
]
SortQuery = Annotated[
    str,
    Query(
        pattern=SORT_PATTERN,
        description=(
            "Columna; prefijo '-' para descendente. Permitidas: risk_score, n_signals, "
            "award_total, year, anomaly_score, buyer_name, ocid."
        ),
    ),
]
