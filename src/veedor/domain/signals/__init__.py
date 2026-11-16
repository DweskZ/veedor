"""Signals v1: definitions, parameters and scoring (pure, no I/O)."""

from veedor.domain.signals.definitions import (
    CONTEXT_CODES,
    RISK_CODES,
    SIGNALS,
    SIGNALS_BY_CODE,
    SignalDefinition,
    get_signal,
)
from veedor.domain.signals.kinds import supplier_kind
from veedor.domain.signals.scoring import MAX_SCORE, SIGNAL_WEIGHTS, risk_score

__all__ = [
    "CONTEXT_CODES",
    "RISK_CODES",
    "MAX_SCORE",
    "SIGNALS",
    "SIGNALS_BY_CODE",
    "SIGNAL_WEIGHTS",
    "SignalDefinition",
    "get_signal",
    "risk_score",
    "supplier_kind",
]
