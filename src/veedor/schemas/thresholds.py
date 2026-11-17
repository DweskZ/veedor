"""Schemas of the threshold context endpoints (context only, never a risk signal)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Bunching(BaseModel):
    status: str = Field(description="estimated, insufficient_data, fit_failed o not_analysable.")
    n_window: int = Field(description="Procesos con presupuesto dentro de +/-20 % del umbral.")
    excess_bins: float | None = Field(
        None,
        description="Exceso observado menos contrafactual en el 5 % "
        "bajo el umbral, en unidades de un tramo contrafactual.",
    )
    excess_bins_ci_low: float | None = None
    excess_bins_ci_high: float | None = None
    excess_pct: float | None = Field(None, description="Exceso relativo al contrafactual, en %.")
    missing_above_pct: float | None = Field(
        None, description="Procesos faltantes en el 5 % sobre el umbral, en %."
    )


class ThresholdStat(BaseModel):
    year: int
    category: str = Field(examples=["goods_services"])
    threshold_code: str = Field(examples=["GS_MENOR_COTIZACION"])
    procedure_below: str
    procedure_above: str
    coefficient: str = Field(description="Coeficiente del PIE, o 'fixed' desde la reforma de 2025.")
    threshold_usd: float
    source_url: str = Field(description="Publicación oficial del SERCOP de donde proviene el valor.")
    source_note: str
    verification: str
    n_band_below: int = Field(description="Procesos con presupuesto en el 5 % bajo el umbral (inclusive).")
    n_band_above: int = Field(description="Procesos con presupuesto en el 5 % sobre el umbral.")
    bunching: Bunching
    caveats: list[str] = Field(default_factory=list)


class ThresholdStats(BaseModel):
    items: list[ThresholdStat]
    band_pct: float
    excluded_years: dict[str, str]
    notes: list[str]
    data_built_at: str | None = None


class ProcessThresholdInfo(BaseModel):
    code: str
    category: str
    threshold_usd: float
    procedure_below: str
    procedure_above: str
    coefficient: str
    source_url: str
    verification: str


class ProcessThreshold(BaseModel):
    ocid: str
    year: int | None
    budget: float | None
    applicable: bool
    reason_code: str | None = None
    reason: str | None = None
    threshold: ProcessThresholdInfo | None = None
    distance_to_threshold_pct: float | None = Field(
        None, description="(umbral - presupuesto) / umbral x 100 para el umbral inmediatamente superior."
    )
    just_below: bool | None = Field(
        None,
        description="Verdadero si el presupuesto está en o bajo el umbral y a 2 % o menos de él. Es "
        "una descripción neutra, no una conclusión.",
    )
    band_pct: float
    notes: list[str]
