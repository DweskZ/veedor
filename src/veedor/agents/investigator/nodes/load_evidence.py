"""Deterministic data gathering. Runs before any model: the LLM never touches the lake."""

from __future__ import annotations

from collections.abc import Callable

from veedor.agents.investigator.state import InvestigatorState
from veedor.domain.dossier.errors import ProcessNotFoundError
from veedor.domain.dossier.models import EvidencePack

EvidenceLoader = Callable[[str], EvidencePack | None]


def load_evidence(state: InvestigatorState, *, loader: EvidenceLoader) -> dict:
    pack = loader(state["ocid"])
    if pack is None:
        raise ProcessNotFoundError(state["ocid"])
    return {"pack": pack}
