"""Comparison of one process with the others of its method and year (no interpretation)."""

from __future__ import annotations

from pydantic import BaseModel, Field

PERCENTILE_NOTE = (
    "percentile: porcentaje de los procesos comparables (mismo método y año, con este dato) cuyo valor "
    "es menor o igual al de este proceso, de 0 a 100."
)


class Reasoned(BaseModel):
    reason_code: str | None = Field(
        None,
        description="Motivo por el que el valor es nulo: not_published_for_procedure (el procedimiento no "
        "publica el dato) o not_available_for_process (este proceso no lo tiene).",
        examples=["not_published_for_procedure"],
    )
    reason: str | None = Field(None, description="Motivo en español, para mostrar.")


class TendererBucket(BaseModel):
    bucket: str = Field(description="Número de oferentes: 1, 2, 3, 4, 5 o 6+.", examples=["1"])
    count: int = Field(description="Procesos comparables con ese número de oferentes.")


class TenderersContext(Reasoned):
    value: int | None = Field(None, description="Oferentes de este proceso.", examples=[3])
    percentile: float | None = Field(None, description=PERCENTILE_NOTE, examples=[62.5])
    n: int = Field(description="Procesos comparables con número de oferentes conocido.")
    distribution: list[TendererBucket] = Field(
        description="Conteos para 1, 2, 3, 4, 5 y 6 o más oferentes; vacío si no hay datos."
    )


class Measure(Reasoned):
    value: float | None = Field(None, description="Valor de este proceso.")
    percentile: float | None = Field(None, description=PERCENTILE_NOTE)
    n: int = Field(description="Procesos comparables con este dato.")
    q1: float | None = Field(None, description="Primer cuartil (25 %) de los procesos comparables.")
    median: float | None = Field(None, description="Mediana de los procesos comparables.")
    q3: float | None = Field(None, description="Tercer cuartil (75 %) de los procesos comparables.")


class RatioMeasure(Measure):
    """Monto adjudicado / presupuesto referencial (sin unidad; 1 = igual al presupuesto)."""


class WindowMeasure(Measure):
    """Días entre el inicio y el fin de la recepción de ofertas."""


class ProcessContext(BaseModel):
    ocid: str = Field(examples=["ocds-5wno2w-LICO-GADM-2023-0001"])
    method: str | None = Field(None, description="Método de contratación del proceso.")
    year: int | None = Field(None, description="Año del proceso.")
    comparable_processes: int = Field(description="Procesos del mismo método y año (incluye este).")
    tenderers: TenderersContext = Field(description="Número de oferentes frente a procesos comparables.")
    award_budget_ratio: RatioMeasure = Field(
        description="Monto adjudicado dividido por el presupuesto referencial (procesos con ambos > 0)."
    )
    tender_window_days: WindowMeasure = Field(
        description="Días entre el inicio y el fin de la recepción de ofertas, cuando existen ambas fechas."
    )
