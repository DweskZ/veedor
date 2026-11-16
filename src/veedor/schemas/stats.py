"""Stats endpoint schema."""

from __future__ import annotations

from pydantic import BaseModel, Field

from veedor.schemas.buyers import SignalCount


class ScoreBucket(BaseModel):
    lower: int = Field(description="Inclusive lower bound of the bucket.")
    upper: int = Field(description="Exclusive upper bound (the last bucket includes 100).")
    count: int


class Stats(BaseModel):
    processes_total: int | None = Field(None, description="Rows in the lake (None when not available).")
    processes_by_method_group: dict[str, int] = {}
    processes_scored: int | None = None
    processes_with_signals: int | None = None
    mean_risk_score: float | None = None
    score_distribution: list[ScoreBucket] = []
    signal_counts: list[SignalCount] = Field([], description="Risk signals only.")
    context_signal_counts: list[SignalCount] = Field([], description="Context signals (not in the score).")
    first_year: int | None = None
    last_year: int | None = None
    last_data_date: str | None = None
    available_tables: dict[str, bool]


class RegionStat(BaseModel):
    """Aggregates of the competitive processes whose BUYING entity is in one province."""

    region: str = Field(
        description="Clave canónica de la provincia (mayúsculas, como en los datos), SIN_REGION o NACIONAL.",
        examples=["MANABI"],
    )
    region_label: str = Field(description="Nombre para mostrar, en español.", examples=["Manabí"])
    competitive_processes: int = Field(
        description="Procesos competitivos de las entidades de la provincia (base de los porcentajes).",
        examples=[17268],
    )
    with_signal: int = Field(
        description="Procesos competitivos con al menos una señal de riesgo (las de contexto no cuentan).",
        examples=[5693],
    )
    pct_with_signal: float | None = Field(
        description="with_signal / competitive_processes, en porcentaje (0 a 100). Es un indicador, "
        "no una acusación: más señales no implican más problemas.",
        examples=[32.97],
    )
    single_bidder: int = Field(
        description="Procesos competitivos con la señal Oferente único.", examples=[4766]
    )
    pct_single_bidder: float | None = Field(
        description="single_bidder / competitive_processes, en porcentaje (0 a 100).", examples=[27.6]
    )
    mean_score: float | None = Field(
        description="Puntaje de riesgo medio (0 a 100) de los procesos competitivos.", examples=[6.53]
    )
    processes_total: int = Field(
        description="Todos los procesos de las entidades de la provincia, de cualquier método.",
        examples=[24098],
    )
    awarded_total: float = Field(
        description="Suma de los montos adjudicados (USD) de todos los procesos; los montos nulos se omiten.",
        examples=[2265992118.19],
    )
    small_sample: bool = Field(
        description="True cuando la provincia tiene menos de 500 procesos competitivos: la cifra es "
        "poco estable."
    )


class RegionStats(BaseModel):
    items: list[RegionStat] = Field(
        description="Una fila por provincia de la entidad contratante, más SIN_REGION; orden alfabético."
    )
    national: RegionStat = Field(description="Los mismos campos sobre todo el país.")
    basis: str = Field(description="Base de los porcentajes.", examples=["competitive"])
    data_built_at: str | None = Field(None, description="Momento (UTC) de la última construcción de datos.")
    notes: list[str] = Field(default_factory=list, description="Aclaraciones para mostrar con las cifras.")


class MethodMix(BaseModel):
    competitive: float | None = Field(description="% del monto adjudicado en procesos competitivos.")
    direct: float | None = Field(description="% del monto adjudicado por contratación directa.")
    catalogue: float | None = Field(description="% del monto adjudicado por catálogo electrónico.")
    other: float | None = Field(description="% del monto en otros métodos; las cuatro cifras suman 100.")


class YearStat(BaseModel):
    year: int = Field(examples=[2024])
    processes_total: int = Field(description="Todos los procesos publicados del año.", examples=[179973])
    competitive_processes: int = Field(description="Procesos competitivos del año.", examples=[28000])
    single_bidder_base: int = Field(
        description="Subastas inversas electrónicas del año con número de oferentes conocido "
        "(denominador de pct_single_bidder).",
        examples=[19415],
    )
    single_bidder_count: int = Field(
        description="De esas subastas, las que tuvieron un solo oferente.", examples=[3973]
    )
    pct_single_bidder: float | None = Field(
        description="Porcentaje de subastas inversas electrónicas con un solo oferente "
        "(single_bidder_count / single_bidder_base).",
        examples=[20.46],
    )
    pct_with_signal: float | None = Field(
        description="Porcentaje de procesos competitivos con al menos una señal de riesgo.", examples=[31.5]
    )
    awarded_total: float = Field(
        description="Suma de los montos adjudicados (USD) del año; los montos nulos se omiten."
    )
    method_mix: MethodMix = Field(
        description="Participación de cada grupo de métodos en el monto adjudicado del año."
    )
    partial_year: bool = Field(description="True para el último año si los datos no lo cubren completo.")
    notes: list[str] = Field(default_factory=list, description="Aclaraciones que aplican a este año.")


class YearStats(BaseModel):
    items: list[YearStat] = Field(description="Una fila por año con procesos, en orden ascendente.")
    single_bidder_method: str = Field(
        description="Procedimiento usado para la serie de oferente único.",
        examples=["Subasta Inversa Electrónica"],
    )
    notes: list[str] = Field(description="Aclaraciones generales de la serie, en español.")
    data_built_at: str | None = None
