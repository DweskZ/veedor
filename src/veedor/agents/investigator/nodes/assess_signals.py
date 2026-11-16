"""Deterministic signal assessment: order signals and attach the methodology caveat."""

from __future__ import annotations

from veedor.agents.investigator.state import InvestigatorState
from veedor.domain.dossier.assessment import assess


def assess_signals(state: InvestigatorState) -> dict:
    return {"pack": assess(state["pack"])}
