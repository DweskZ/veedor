"""Verified yearly procedure-amount thresholds of Ecuador's public procurement (context, not a signal).

Until mid-2025 the thresholds are coefficients of the Presupuesto Inicial del Estado (PIE) of the year;
SERCOP publishes the PIE and the resulting dollar figures each year. Every year below was checked
against the official SERCOP publication named in ``source_url`` (see docs/THRESHOLDS.md). From the
2025 reform the thresholds are fixed dollar amounts (USD 10,000). A year that is not verified is not
in ``YEARS`` and has no thresholds: nothing is estimated or interpolated.

Pure data and arithmetic; no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

SERCOP = "https://portal.compraspublicas.gob.ec/sercop/"

GOODS_SERVICES = "goods_services"
WORKS = "works"
CONSULTANCY = "consultancy"

MENOR = "Menor Cuantía"
COTIZACION = "Cotización"
LICITACION = "Licitación"
SIE = "Subasta Inversa Electrónica"
LISTA_CORTA = "Lista corta"
CONCURSO = "Concurso publico"

PIE_REGIME = "pie_coefficients"
FIXED_REGIME = "fixed_usd_after_2025_reform"
PRICE_FIXED_USD = Decimal("10000")


@dataclass(frozen=True, slots=True)
class ThresholdRule:
    """A boundary between two procedures, as a coefficient of the PIE."""

    code: str
    category: str
    coefficient: str
    below: tuple[str, ...]  # lake method names that apply at or below the boundary (may be empty)
    above: tuple[str, ...]
    procedure_below_label: str
    procedure_above_label: str
    analysable: bool  # procedures on both sides are present in the lake


PIE_RULES: tuple[ThresholdRule, ...] = (
    ThresholdRule(
        "GS_INFIMA_SIE",
        GOODS_SERVICES,
        "0.0000002",
        (),
        (SIE,),
        "Ínfima cuantía",
        "Subasta inversa electrónica",
        False,
    ),
    ThresholdRule(
        "GS_MENOR_COTIZACION",
        GOODS_SERVICES,
        "0.000002",
        (MENOR,),
        (COTIZACION,),
        "Menor cuantía",
        "Cotización",
        True,
    ),
    ThresholdRule(
        "GS_COTIZACION_LICITACION",
        GOODS_SERVICES,
        "0.000015",
        (COTIZACION,),
        (LICITACION,),
        "Cotización",
        "Licitación",
        True,
    ),
    ThresholdRule(
        "W_MENOR_COTIZACION", WORKS, "0.000007", (MENOR,), (COTIZACION,), "Menor cuantía", "Cotización", True
    ),
    ThresholdRule(
        "W_COTIZACION_LICITACION",
        WORKS,
        "0.00003",
        (COTIZACION,),
        (LICITACION,),
        "Cotización",
        "Licitación",
        True,
    ),
    ThresholdRule(
        "C_LISTA_CORTA_CONCURSO",
        CONSULTANCY,
        "0.000015",
        (LISTA_CORTA,),
        (CONCURSO,),
        "Lista corta",
        "Concurso público",
        True,
    ),
)

FIXED_RULES: tuple[ThresholdRule, ...] = (
    ThresholdRule(
        "GS_INFIMA_SIE",
        GOODS_SERVICES,
        "fixed",
        (),
        (SIE, LICITACION),
        "Ínfima cuantía",
        "Subasta inversa electrónica / Licitación",
        False,
    ),
    ThresholdRule(
        "W_INFIMA_LICITACION", WORKS, "fixed", (), (LICITACION,), "Ínfima cuantía", "Licitación", False
    ),
    ThresholdRule(
        "C_INFIMA_CONCURSO",
        CONSULTANCY,
        "fixed",
        (),
        (CONCURSO,),
        "Ínfima cuantía",
        "Concurso público",
        False,
    ),
)


@dataclass(frozen=True, slots=True)
class YearSource:
    year: int
    regime: str
    pie: Decimal
    source_url: str
    source_note: str


YEARS: dict[int, YearSource] = {
    y.year: y
    for y in (
        YearSource(
            2015, PIE_REGIME, Decimal("36317117010.35"), SERCOP + "?p=32320", "SERCOP page, montos 2015"
        ),
        YearSource(
            2016, PIE_REGIME, Decimal("29835098320.79"), SERCOP + "?p=32324", "SERCOP page, montos 2016"
        ),
        YearSource(
            2017,
            PIE_REGIME,
            Decimal("29835098320.79"),
            SERCOP + "?p=32328",
            "SERCOP page, montos 2017 (same PIE as 2016 in the source)",
        ),
        YearSource(
            2018, PIE_REGIME, Decimal("34853371653.72"), SERCOP + "?p=32334", "SERCOP page, montos 2018"
        ),
        YearSource(
            2019, PIE_REGIME, Decimal("35529394461.72"), SERCOP + "?p=35906", "SERCOP page, montos 2019"
        ),
        YearSource(
            2020, PIE_REGIME, Decimal("35498420637.20"), SERCOP + "?p=39607", "SERCOP page, montos 2020"
        ),
        YearSource(
            2021,
            PIE_REGIME,
            Decimal("32080363387.48"),
            SERCOP + "montos-de-contratacion-publica-2021/",
            "SERCOP page, montos 2021",
        ),
        YearSource(
            2022,
            PIE_REGIME,
            Decimal("33899734759.85"),
            SERCOP + "wp-content/uploads/2022/01/montos_contratacion_2022-2-1.pdf",
            "SERCOP PDF, montos 2022",
        ),
        YearSource(
            2023,
            PIE_REGIME,
            Decimal("31502865593.76"),
            SERCOP + "wp-content/uploads/2023/01/montos_contratacion_2023.pdf",
            "SERCOP PDF, montos 2023",
        ),
        YearSource(
            2024,
            PIE_REGIME,
            Decimal("33296819775.31"),
            SERCOP + "wp-content/uploads/2024/01/montos_contratacion_2024.pdf",
            "SERCOP PDF, montos 2024",
        ),
        YearSource(
            2026,
            FIXED_REGIME,
            Decimal("46255572824.33"),
            SERCOP + "wp-content/uploads/2026/01/INFOGRAFIA-MONTOS-2026-01.png",
            "SERCOP infographic (image), montos 2026",
        ),
    )
}

# 2025 has a published table before the reform and another after it, inside one calendar year, and the
# procedures in force between 3 and 7 October 2025 are not documented in a source read here: the year is
# deliberately left out rather than mixed.
EXCLUDED_YEARS: dict[int, str] = {
    2025: "The regime changed inside the year (coefficient table until June, fixed USD 10,000 from the "
    "reform); no single-year table is used."
}


@dataclass(frozen=True, slots=True)
class Threshold:
    year: int
    code: str
    category: str
    coefficient: str
    value_usd: float
    below: tuple[str, ...]
    above: tuple[str, ...]
    procedure_below_label: str
    procedure_above_label: str
    analysable: bool
    source_url: str
    source_note: str
    regime: str


def _usd(amount: Decimal) -> float:
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def thresholds_for(year: int) -> list[Threshold]:
    """Verified thresholds of a year; empty when the year is not verified."""
    src = YEARS.get(year)
    if src is None:
        return []
    rules = PIE_RULES if src.regime == PIE_REGIME else FIXED_RULES
    out = []
    for r in rules:
        value = src.pie * Decimal(r.coefficient) if src.regime == PIE_REGIME else PRICE_FIXED_USD
        out.append(
            Threshold(
                year,
                r.code,
                r.category,
                r.coefficient,
                _usd(value),
                r.below,
                r.above,
                r.procedure_below_label,
                r.procedure_above_label,
                r.analysable,
                src.source_url,
                src.source_note,
                src.regime,
            )
        )
    return out


def all_thresholds() -> list[Threshold]:
    return [t for year in sorted(YEARS) for t in thresholds_for(year)]


def category_of(lake_category: str | None, method: str | None) -> str | None:
    """Threshold category of a process: consultancy by its procedure name, else the lake category."""
    if method in (LISTA_CORTA, CONCURSO):
        return CONSULTANCY
    return {"goods": GOODS_SERVICES, "services": GOODS_SERVICES, "works": WORKS}.get(lake_category or "")
