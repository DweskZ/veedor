"""Pydantic models of the tool results the investigation reads (pure, shapes taken from real output).

Every model ignores unknown keys, so a field that is not declared here (a legal representative's name,
an address, a phone number) is dropped at validation time and can never be stored. Fields are
length-capped: a hostile or oversized value makes the result invalid instead of being truncated.
Declared strings are only ever mapped to closed vocabularies or parsed into numbers and dates by the
specialists; none is copied into a pack.
"""

from __future__ import annotations

import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RUC_PATTERN = re.compile(r"^[0-9]{13}$")
# Shape of a Contraloría report number ("Nº Informe"), derived from the 25 captured rows of the source:
# an office code (2-6 capitals and an optional digit: DPB, DNA3, DR1, DAI), up to three further
# capital groups (AI, DPM), a 3-5 digit sequence and the four-digit year: DPB-0001-2022, DNA3-0001-2022,
# DNA1-DPM-AI-0001-2023. Anything else (a cédula, a RUC, free text) is shown as unavailable.
REPORT_ID_PATTERN = re.compile(r"^[A-Z]{2,6}[0-9]?(?:-[A-Z]{1,6}[0-9]?){0,3}-[0-9]{3,5}-(?:19|20)[0-9]{2}$")
CATALOGUE_ID_PATTERN = re.compile(r"^[0-9]{1,6}$")
MAX_TEXT = 400
MAX_YEARS = 60
MAX_ROWS = 500
MAX_CATALOGUE = 100
FIRST_PLAUSIBLE_YEAR = 1800

_DMY_SLASH = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DMY_DASH = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$")


def parse_day(text: str | None) -> date | None:
    """A real calendar date in day-first (``19/12/2014``, ``30-09-2010``) or ISO form, else None.

    Plausibility (1900 to today) is not decided here: `domain.investigation.bounds` does it.
    """
    if text is None:
        return None
    value = text.strip()
    for pattern, order in ((_ISO, "ymd"), (_DMY_SLASH, "dmy"), (_DMY_DASH, "dmy")):
        match = pattern.match(value)
        if match:
            a, b, c = (int(g) for g in match.groups())
            year, month, day = (a, b, c) if order == "ymd" else (c, b, a)
            try:
                parsed = date(year, month, day)
            except ValueError:
                return None
            return parsed
    return None


def parse_amount(text: str | int | float | None) -> float | None:
    """An amount written like ``400,00`` or ``1.234,56`` (or already a number); range is checked later."""
    if text is None or isinstance(text, bool):
        return None
    if isinstance(text, int | float):
        return float(text) if math.isfinite(text) else None
    value = text.strip().replace(" ", "")
    if not value:
        return None
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return float(number) if number.is_finite() else None


def parse_year(text: str | int | None) -> int | None:
    if text is None or isinstance(text, bool):
        return None
    value = str(text).strip()
    return int(value) if re.fullmatch(r"\d{4}", value) and int(value) >= FIRST_PLAUSIBLE_YEAR else None


class _Result(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CompaniaInfo(_Result):
    """`get_compania_info(ruc, format="json")` (Superintendencia de Compañías directory record)."""

    ruc: str = Field(pattern=RUC_PATTERN.pattern)
    situacion_legal: str | None = Field(default=None, max_length=MAX_TEXT)
    fecha_constitucion: str | None = Field(default=None, max_length=40)
    capital_suscrito: str | int | float | None = None
    ultimo_balance: str | int | None = Field(default=None)


class SriRucInfo(_Result):
    """`get_sri_ruc_info(ruc, include_establecimientos=False, format="json")`."""

    ruc: str = Field(pattern=RUC_PATTERN.pattern)
    estado: str | None = Field(default=None, max_length=MAX_TEXT)
    clase_contribuyente: str | None = Field(default=None, max_length=MAX_TEXT)
    categoria_mipymes: str | None = Field(default=None, max_length=MAX_TEXT)
    fecha_inicio_actividades: str | None = Field(default=None, max_length=40)
    fecha_cese_actividades: str | None = Field(default=None, max_length=40)


class FinancialYear(_Result):
    anio: int = Field(ge=FIRST_PLAUSIBLE_YEAR, le=2200)
    ingresos_ventas: float | None = None
    activos: float | None = None
    patrimonio: float | None = None
    n_empleados: int | None = None


class Financials(_Result):
    """`get_financials(expediente_or_ruc, format="json")`."""

    ruc: str = Field(pattern=RUC_PATTERN.pattern)
    years: list[FinancialYear] = Field(default_factory=list, max_length=MAX_YEARS)


class CatalogueEntry(_Result):
    id: str = Field(pattern=CATALOGUE_ID_PATTERN.pattern)
    tipo: str | None = Field(default=None, max_length=40)
    label: str = Field(max_length=MAX_TEXT)


class Catalogue(_Result):
    """`list_catalogo(fuente="contraloria", format="json")`."""

    fuente: str | None = Field(default=None, max_length=40)
    informes: list[CatalogueEntry] = Field(default_factory=list, max_length=MAX_CATALOGUE)


class ReportsFile(_Result):
    """`get_contraloria_informe(informe_id, rows, format="json")`: a preview, capped by the server."""

    headers: list[str] = Field(default_factory=list, max_length=40)
    rows: list[list[str | int | float | None]] = Field(default_factory=list, max_length=MAX_ROWS)
    total_rows_in_preview: int | None = None
    truncated: bool | None = None
    label: str | None = Field(default=None, max_length=MAX_TEXT)

    @field_validator("headers", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> object:
        return [str(v) for v in value] if isinstance(value, list) else value


class PairAwards(_Result):
    """Local tool `pair_awards`: other awards between a buyer and a supplier, from the lake."""

    n_other_awards: int = Field(ge=0)
    n_with_amount: int = Field(ge=0)
    total_other_amount: float | None = None


class SimilarSummary(_Result):
    """Local tool `similar_processes`: same-buyer neighbours near the process date."""

    neighbours_examined: int = Field(ge=0)
    n_above_floor: int = Field(ge=0)
    basis: Literal["description", "classification"]
    n_in_window: int = Field(ge=0)
    n_with_amount: int = Field(ge=0)
    combined_amount: float | None = None


class EnquirySummary(_Result):
    """`process_texts` (local tool): counts and dates of the process's own enquiries. No text, no names."""

    n_with_text: int = Field(ge=0, le=100_000)
    n_answered: int = Field(ge=0, le=100_000)
    n_dated_pairs: int = Field(ge=0, le=100_000)
    median_days_to_answer: float | None = Field(default=None, ge=0, le=3_650)
    max_days_to_answer: int | None = Field(default=None, ge=0, le=3_650)
    n_late: int | None = Field(default=None, ge=0, le=100_000)
    topic_deadlines: int = Field(ge=0, le=100_000)
    topic_specifications: int = Field(ge=0, le=100_000)
    topic_price: int = Field(ge=0, le=100_000)
    topic_requirements: int = Field(ge=0, le=100_000)
