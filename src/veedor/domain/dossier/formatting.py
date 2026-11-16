"""Spanish number, date and text formatting used by the template (pure)."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from veedor.domain.dossier.vocabulary import MONTHS_ES, NOT_AVAILABLE

CATEGORY_ES = {
    "goods": "bienes",
    "services": "servicios",
    "works": "obras",
    "consultingServices": "consultoría",
}
STATUS_ES = {
    "planning": "en planificación",
    "planned": "planificado",
    "active": "activo",
    "cancelled": "cancelado",
    "unsuccessful": "desierto",
    "complete": "completado",
    "withdrawn": "retirado",
}


def _swap_separators(text: str) -> str:
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def fmt_decimal(value: float, decimals: int) -> str:
    quantum = Decimal(1).scaleb(-decimals)
    rounded = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    return _swap_separators(f"{rounded:,.{decimals}f}")


def fmt_usd(value: float | None) -> str:
    return NOT_AVAILABLE if value is None else f"USD {fmt_decimal(value, 2)}"


def fmt_num(value: float | int | None, max_decimals: int = 4) -> str:
    """Exact when the value has at most `max_decimals` decimals, otherwise rounded to exactly that many."""
    if value is None:
        return NOT_AVAILABLE
    exact = Decimal(str(value))
    decimals = max(0, -exact.normalize().as_tuple().exponent)
    return fmt_decimal(float(value), min(decimals, max_decimals))


def fmt_times(value: float) -> str:
    """A multiple ('260,9 veces'): one decimal from 10 up, two below, so the rounding stays honest."""
    return f"{fmt_num(value, 1 if abs(value) >= 10 else 2)} veces"


def fmt_count(value: float | int, one: str, many: str, max_decimals: int = 4) -> str:
    """A count with its noun in the right number: ``1 día``, ``0 días``, ``2 días``."""
    return f"1 {one}" if value == 1 else f"{fmt_num(value, max_decimals)} {many}"


def fmt_pct(ratio: float | None, decimals: int = 1) -> str:
    if ratio is None:
        return NOT_AVAILABLE
    return f"{fmt_decimal(float(Decimal(str(ratio)) * 100), decimals)} %"


def fmt_date(iso: str | None) -> str:
    if not iso:
        return NOT_AVAILABLE
    try:
        parsed = date.fromisoformat(iso[:10])
    except ValueError:
        return NOT_AVAILABLE
    return f"{parsed.day} de {MONTHS_ES[parsed.month - 1]} de {parsed.year}"


def fmt_text(value: str | None) -> str:
    return NOT_AVAILABLE if value is None or not value.strip() else value.strip()


def quote(value: str | None, limit: int = 280) -> str:
    """Verbatim excerpt between « » (prefix cut at a word boundary), or `no disponible`."""
    if value is None or not value.strip():
        return NOT_AVAILABLE
    text = " ".join(value.replace("«", '"').replace("»", '"').split())
    if len(text) <= limit:
        return f"«{text}»"
    cut = text[:limit].rsplit(" ", 1)[0]
    return f"«{cut}»…"


def fmt_year(year: int | None) -> str:
    return NOT_AVAILABLE if year is None else str(year)
