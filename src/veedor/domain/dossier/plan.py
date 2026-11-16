"""Constrained generation vocabulary: what a model may choose, and nothing else.

A model never writes text about facts. It returns a `RenderPlan`: an order of fact identifiers (from
the catalogue built out of the evidence pack), at most one connective phrase per section and at most
one reviewer note, both chosen from the closed sets below. The renderer writes every sentence.

Each phrase carries an applicability predicate. A phrase is offered to the model, and accepted in a
plan, only when its predicate holds for the pack (and the section, for connectives).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from veedor.domain.dossier.vocabulary import (
    SECTION_CONTEXT,
    SECTION_REGISTRAL,
    SECTION_RELATION,
)


@dataclass(frozen=True)
class Phrase:
    text: str
    applies: Callable[[Any, str | None], bool]  # (EvidencePack, section title or None) -> bool


def _always(pack: Any, section: str | None) -> bool:
    return True


def _context_sections(pack: Any, section: str | None) -> bool:
    return section in (SECTION_CONTEXT, SECTION_REGISTRAL, SECTION_RELATION)


def _has_risk_signals(pack: Any, section: str | None) -> bool:
    return pack.n_risk_signals > 0


def _has_company_winner(pack: Any, section: str | None) -> bool:
    w = pack.winner
    return w is not None and bool(w.ruc) and w.kind in ("company", "public_entity", "other")


def _has_comparison(pack: Any, section: str | None) -> bool:
    c = pack.comparison
    return c is not None and any(
        v is not None for v in (c.n_processes, c.median_tenderers, c.single_bidder_share)
    )


CONNECTIVES: dict[str, Phrase] = {
    "conn:detalle": Phrase("A continuación se detallan los hechos de esta sección.", _always),
    "conn:contexto": Phrase("Los siguientes datos aportan contexto para la revisión.", _context_sections),
    "conn:contrastar": Phrase("Estos datos deben contrastarse con la fuente oficial.", _always),
}

REVIEWER_NOTES: dict[str, Phrase] = {
    "senales": Phrase(
        "Nota para quien revisa: conviene comenzar por las señales detectadas y contrastarlas con los "
        "documentos del proceso.",
        _has_risk_signals,
    ),
    "proveedor": Phrase(
        "Nota para quien revisa: conviene comenzar por verificar los datos del proveedor adjudicado en "
        "las fuentes oficiales.",
        _has_company_winner,
    ),
    "contexto": Phrase(
        "Nota para quien revisa: conviene comparar este proceso con el contexto de procesos similares.",
        _has_comparison,
    ),
    "sin_prioridad": Phrase(
        "Nota para quien revisa: no se sugiere una prioridad entre los hechos presentados.", _always
    ),
}


def applicable_connectives(pack: Any, section: str | None = None) -> dict[str, Phrase]:
    return {i: p for i, p in CONNECTIVES.items() if p.applies(pack, section)}


def applicable_notes(pack: Any) -> dict[str, Phrase]:
    return {i: p for i, p in REVIEWER_NOTES.items() if p.applies(pack, None)}


class PlanError(ValueError):
    """The plan references something that is not in the catalogue or the closed sets."""


@dataclass
class RenderPlan:
    sections: dict[str, list[str]] = field(default_factory=dict)  # section title -> fact/connective ids
    summary_signal_order: list[str] = field(default_factory=list)  # signal codes
    reviewer_note: str | None = None
