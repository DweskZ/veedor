"""Methodology caveats per signal and signal ordering (pure)."""

from __future__ import annotations

from veedor.domain.dossier.models import SignalFact
from veedor.domain.dossier.vocabulary import CONTEXT_SIGNAL_CODES

DEFAULT_CAVEAT = "Es un indicador de riesgo y requiere verificación humana."

CAVEATS: dict[str, str] = {
    "SINGLE_BIDDER": "Un solo oferente puede deberse a proveedores exclusivos; requiere verificación humana.",
    "SHORT_TENDER_WINDOW": "El umbral es estadístico, calculado sobre procesos del mismo método y año.",
    "LOW_SAVING": "Un ahorro bajo puede reflejar un presupuesto bien estimado; el umbral es estadístico.",
    "NEW_SUPPLIER": "Compara la fecha de inicio de actividades del SRI con la primera adjudicación.",
    "SUPPLIER_NOT_ACTIVE": (
        "Se basa en el estado actual del SRI, no en el estado vigente al momento de la adjudicación."
    ),
    "GHOST_COMPANY_LIST": "Depende de la versión del listado publicado por el SRI que se haya obtenido.",
    "BUYER_CONCENTRATION": "La concentración puede explicarse por la naturaleza de la compra.",
    "REPEATED_DIRECT_AWARDS": "Las adjudicaciones repetidas pueden responder a necesidades recurrentes.",
    "RECURRING_COBIDDERS": "La coincidencia entre oferentes puede deberse a un mercado reducido.",
    "CONTRACT_VS_COMPANY_SIZE": "Depende de los ingresos reportados a la Superintendencia de Compañías.",
}

SIGNAL_ORDER: tuple[str, ...] = tuple(CAVEATS)


def caveat_for(code: str) -> str:
    return CAVEATS.get(code, DEFAULT_CAVEAT)


def order_and_annotate(signals: list[SignalFact]) -> list[SignalFact]:
    """Deterministic order (catalogue order, then code) with the methodology caveat attached."""
    rank = {code: i for i, code in enumerate(SIGNAL_ORDER)}
    ordered = sorted(signals, key=lambda s: (rank.get(s.code, len(rank)), s.code))
    return [s.model_copy(update={"caveat": caveat_for(s.code)}) for s in ordered]


def is_informational(signal: SignalFact) -> bool:
    """Context signals, and a registry listing published after the process, carry no risk weight."""
    if signal.code in CONTEXT_SIGNAL_CODES:
        return True
    later = signal.evidence.get("listed_after_process", signal.evidence.get("listed_after_award"))
    return signal.code == "GHOST_COMPANY_LIST" and later is True
