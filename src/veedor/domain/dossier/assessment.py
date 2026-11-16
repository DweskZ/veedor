"""Deterministic signal assessment: ordering and methodology caveats (pure)."""

from __future__ import annotations

from veedor.domain.dossier.models import EvidencePack
from veedor.domain.dossier.signal_text import order_and_annotate


def assess(pack: EvidencePack) -> EvidencePack:
    return pack.model_copy(update={"signals": order_and_annotate(pack.signals)})
