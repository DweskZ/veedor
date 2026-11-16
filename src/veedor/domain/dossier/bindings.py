"""Label -> value bindings: a figure that directly follows a known label must be that label's value.

A ratio label accepts the figure as a percentage (``97,1 %``) or as the plain decimal fraction
(``0,9706``), whichever form is used must equal the pack value at the precision shown.

Membership alone lets an LLM swap two real figures (budget and award) without detection. For every
label phrase below, when a number or date appears right after the phrase (only filler words such as
``de``, ``fue``, ``USD`` or punctuation in between), it must equal one of the values the pack holds
for that phrase. Figures that do not directly follow a known label are checked by membership only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from veedor.domain.dossier.text import fold_chars

if TYPE_CHECKING:
    from veedor.domain.dossier.models import EvidencePack

_FILLERS = (
    r"(?:[\s:(\[,\-–—=]|\b(?:de|del|fue|fueron|es|son|por|a|un|total|asciende|ascendio|igual|usd|dolares"
    r"|era|que|ha|sido|el|en|al)\b|\$)*"
)


@dataclass(frozen=True)
class Binding:
    phrases: tuple[str, ...]
    kind: str  # "amount" | "ratio" (fractions) | "count" | "date"
    values: tuple[Decimal | date, ...]
    pattern: re.Pattern[str]


def _binding(phrases: tuple[str, ...], kind: str, values: list[Any]) -> Binding:
    folded = sorted((fold_chars(p) for p in phrases), key=len, reverse=True)
    pattern = re.compile(r"(?:" + "|".join(re.escape(p) for p in folded) + r")" + _FILLERS + r"$")
    return Binding(phrases, kind, tuple(v for v in values if v is not None), pattern)


def _dec(value: float | int | None, scale: int = 1) -> Decimal | None:
    return None if value is None else Decimal(str(value)) * scale


def _day(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


def _evidence(pack: EvidencePack, key: str) -> list[Any]:
    return [s.evidence[key] for s in pack.signals if isinstance(s.evidence.get(key), int | float | str)]


def build_bindings(pack: EvidencePack) -> list[Binding]:
    p, w, h, c = pack.process, pack.winner, pack.history, pack.comparison
    r = w.registry if w else None
    inv = pack.investigation
    co = inv.company if inv else None
    fin = inv.financials if inv else None
    pair = inv.pair_history if inv else None
    sim = inv.similar if inv else None
    num = lambda keys: [_dec(v) for v in keys]  # noqa: E731
    days = lambda *values: [_day(v) for v in values if isinstance(v, str)]  # noqa: E731
    ev = lambda key: _evidence(pack, key)  # noqa: E731
    return [
        _binding(("presupuesto referencial", "presupuesto"), "amount", num([p.budget, *ev("budget")])),
        _binding(
            (
                "monto adjudicado",
                "valor adjudicado",
                "importe adjudicado",
                "adjudicación total",
                "monto de la adjudicación",
            ),
            "amount",
            num([p.award_total, *ev("award_total")]),
        ),  # fmt: skip
        _binding(("ingresos más recientes reportados",), "amount", num([r.latest_revenue] if r else [])),
        _binding(("ingresos del año del proceso",), "amount", num([r.revenue_award_year] if r else [])),
        _binding(
            ("ingresos reportados", "ingresos anuales"),
            "amount",
            num([r.latest_revenue, r.revenue_award_year, *ev("revenue")] if r else ev("revenue")),
        ),
        _binding(("por un total de",), "amount", num([h.total_previous_amount] if h else [])),
        _binding(
            ("relación entre monto adjudicado y presupuesto",),
            "ratio",
            [_dec(v) for v in [p.award_budget_ratio, *ev("award_to_budget")]],
        ),
        _binding(
            ("proporción de procesos con un solo oferente",),
            "ratio",
            [_dec(c.single_bidder_share)] if c else [],
        ),
        _binding(
            ("mediana de la relación entre monto adjudicado y presupuesto", "mediana de la relación"),
            "ratio",
            [_dec(c.median_award_budget_ratio)] if c else [],
        ),
        _binding(("número de oferentes",), "count", num([p.n_tenderers, *ev("n_tenderers")])),
        _binding(("mediana de oferentes",), "count", num([c.median_tenderers] if c else [])),
        _binding(
            (
                "fecha de adjudicación",
                "fecha de la primera adjudicación",
                "se adjudicó el",
                "adjudicado el",
                "adjudicó el",
                "fue adjudicado el",
            ),
            "date",
            days(p.first_award_date, *ev("first_award_date")),
        ),  # fmt: skip
        _binding(("fecha de firma", "se firmó el", "firmado el", "firmó el"), "date", days(p.date_signed)),
        _binding(("inicio de ofertas",), "date", days(p.tender_start, *ev("tender_start"))),
        _binding(("cierre de ofertas",), "date", days(p.tender_end, *ev("tender_end"))),
        _binding(
            ("inicio de actividades", "inició actividades el", "inicio actividades el"),
            "date",
            days(r.activity_start_date if r else None, *ev("activity_start_date")),
        ),  # fmt: skip
        _binding(
            ("fecha de suspensión", "se suspendió el", "suspendido el"),
            "date",
            days(r.suspension_date if r else None, *ev("suspension_date")),
        ),
        _binding(("capital suscrito",), "amount", num([co.subscribed_capital] if co else [])),
        _binding(("fecha de constitución",), "date", days(co.incorporation_date if co else None)),
        _binding(("patrimonio",), "amount", num([fin.equity] if fin else [])),
        _binding(("activos",), "amount", num([fin.assets] if fin else [])),
        _binding(("empleados reportados",), "count", num([fin.employees] if fin else [])),
        _binding(
            ("monto acumulado de esas adjudicaciones",),
            "amount",
            num([pair.total_other_amount] if pair else []),
        ),
        _binding(("su monto combinado",), "amount", num([sim.combined_amount] if sim else [])),
        _binding(("primera adjudicación previa",), "date", days(h.first_award_date if h else None)),
        _binding(("última adjudicación previa",), "date", days(h.last_award_date if h else None)),
    ]


# --- nouns, roles and claims ----------------------------------------------------------------


@dataclass(frozen=True)
class NounBinding:
    """A count written right before a noun must be one of the pack values for that noun."""

    noun: str
    pattern: re.Pattern[str]
    values: tuple[Decimal, ...]


@dataclass(frozen=True)
class RoleBinding:
    """A name written right after a role label must be a pack name of that role."""

    role: str
    pattern: re.Pattern[str]  # label + fillers at the end of the text before the name
    strong: re.Pattern[str]  # label followed by ':' or 'es/fue', then the value
    names: tuple[str, ...]  # folded names allowed for the role


_NOUNS = {
    "oferentes": r"oferentes?",
    "adjudicaciones": r"adjudicacion(?:es)?",
    "procesos": r"procesos?",
    "señales": r"senales?",
    "días": r"dias?",
    "años": r"anos?",
    "proveedores": r"proveedor(?:es)?",
    "veces": r"veces",
}
ROLE_PHRASES = {
    "winner": (
        "proveedor adjudicado",
        "adjudicado a",
        "adjudico a",
        "adjudicatario",
        "ganador",
        "contratista",
    ),
    "buyer": ("entidad contratante", "la entidad", "contratante", "comprador"),
}
_STRONG = {"winner": ("proveedor adjudicado", "adjudicatario"), "buyer": ("entidad contratante",)}
CONTINUATIONS = ("no disponible", "persona natural", "sin identificar")


def build_noun_bindings(pack: EvidencePack) -> list[NounBinding]:
    p, w, h, c = pack.process, pack.winner, pack.history, pack.comparison
    ev = lambda *keys: [v for k in keys for v in _evidence(pack, k)]  # noqa: E731
    from veedor.domain.dossier.signal_text import is_informational

    inv = pack.investigation
    co = inv.company if inv else None
    pair = inv.pair_history if inv else None
    sim = inv.similar if inv else None
    days_inc = co.days_incorporation_to_process if co else None
    incorporation_days = abs(days_inc) if days_inc else None

    n_context = sum(1 for s in pack.signals if is_informational(s))
    values: dict[str, list[Any]] = {
        "oferentes": [
            p.n_tenderers, c.median_tenderers if c else None,
            *ev("n_tenderers", "n_recurring_cobidders_in_process"),
        ],
        "adjudicaciones": [
            p.n_awards, h.n_previous_awards if h else None, h.n_pair_awards if h else None,
            pair.n_other_awards if pair else None,
            *ev("n_awards_buyer_year"),
        ],
        "procesos": [
            c.n_processes if c else None,
            *ev("n_in_window", "n_same_buyer_supplier_cpc", "n_meetings", "n_method_year"),
        ],
        "señales": [pack.n_signals, pack.n_signals - n_context, n_context],
        "días": [
            *ev("window_days", "p05_days", "days_between"),
            incorporation_days,
            sim.window_days if sim else None,
        ],
        "años": [],
        "proveedores": [w.n_award_suppliers if w else None],
        "veces": [
            *ev("ratio", "factor"),
            co.award_to_capital_times if co and (co.award_to_capital_times or 0) >= 0.01 else None,
            0.01,
        ],
    }  # fmt: skip
    return [
        NounBinding(
            noun, re.compile(rf"^\s+(?:{_NOUNS[noun]})\b"), tuple(d for v in vs if (d := _dec(v)) is not None)
        )
        for noun, vs in values.items()
    ]


def build_role_bindings(pack: EvidencePack) -> list[RoleBinding]:
    w, p = pack.winner, pack.process
    names = {
        "winner": [n for n in ([w.name, w.registry.legal_name] if w else []) if n],
        "buyer": [p.buyer_name] if p.buyer_name else [],
    }
    out = []
    for role, phrases in ROLE_PHRASES.items():
        alt = "|".join(re.escape(x) for x in sorted(phrases, key=len, reverse=True))
        strong = "|".join(re.escape(x) for x in _STRONG[role])
        out.append(
            RoleBinding(
                role,
                re.compile(rf"(?:{alt})" + _FILLERS + r"$"),
                re.compile(rf"(?:{strong})\s*(?::|\bes\b|\bfue\b)\s*"),
                tuple(fold_chars(n) for n in names[role]),
            )
        )
    return out
