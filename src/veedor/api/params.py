"""Edge validation for path and query parameters (strict patterns, bounded lengths)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from fastapi import Path, Query

from veedor.domain.regions import REGION_KEYS
from veedor.domain.signals import SIGNALS_BY_CODE

OCID_PATTERN = r"^ocds-5wno2w-[A-Za-z0-9._\-]{1,120}$"
RUC_PATTERN = r"^[0-9]{13}$"
METHOD_PATTERN = r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ .,()/\-]{1,120}$"
SORT_PATTERN = r"^[+-]?[a-z_]{1,30}$"
MIN_YEAR, MAX_YEAR = 2000, 2100
MAX_QUERY_LENGTH = 80

SignalCode = StrEnum("SignalCode", {code: code for code in SIGNALS_BY_CODE})
# Closed set: the 24 province keys used by the lake plus SIN_REGION (buyers without a province).
RegionKey = StrEnum("RegionKey", {key.replace(" ", "_"): key for key in REGION_KEYS})

OcidPath = Annotated[str, Path(pattern=OCID_PATTERN, description="Identificador OCDS del proceso.")]
RucPath = Annotated[str, Path(pattern=RUC_PATTERN, description="RUC de 13 dígitos.")]

YearQuery = Annotated[int | None, Query(ge=MIN_YEAR, le=MAX_YEAR)]
MethodQuery = Annotated[str | None, Query(pattern=METHOD_PATTERN, description="Método de contratación.")]
BuyerRucQuery = Annotated[str | None, Query(pattern=RUC_PATTERN)]
MinScoreQuery = Annotated[float | None, Query(ge=0, le=100)]
# Awarded amount in USD. The upper bound is far above any real contract (the largest awarded total in the
# data is under 1e10) and keeps every value a finite, comparable DOUBLE.
MAX_AMOUNT = 1e12
MinAmountQuery = Annotated[
    float | None,
    Query(ge=0, le=MAX_AMOUNT, allow_inf_nan=False, description="Monto adjudicado mínimo (USD, desde 0)."),
]
MaxAmountQuery = Annotated[
    float | None,
    Query(ge=0, le=MAX_AMOUNT, allow_inf_nan=False, description="Monto adjudicado máximo (USD, desde 0)."),
]
RegionQuery = Annotated[
    RegionKey | None,
    Query(
        description="Provincia de la entidad contratante: clave canónica (p. ej. MANABI, LOS RIOS) o "
        "SIN_REGION para entidades sin provincia registrada."
    ),
]
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
WithSignalsQuery = Annotated[
    bool | None,
    Query(
        description="true: solo procesos con al menos una señal de riesgo; false: solo sin señales; "
        "omitido: cualquiera."
    ),
]
BuyerSearchLimit = Annotated[int, Query(ge=1, le=10, description="Máximo de entidades (1 a 10).")]
