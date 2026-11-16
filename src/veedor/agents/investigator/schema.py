"""Structured plan the model must return; anything that does not parse is rejected.

The model selects and orders catalogue fact ids and picks from closed sets. It writes no sentence.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from veedor.domain.dossier.plan import RenderPlan
from veedor.domain.dossier.vocabulary import (
    SECTION_CONTEXT,
    SECTION_REGISTRAL,
    SECTION_RELATION,
    SECTION_SIGNALS,
    SECTION_WHAT,
    SECTION_WINNER,
)

SECTION_KEYS = {
    "que_se_contrato": SECTION_WHAT,
    "senales_detectadas": SECTION_SIGNALS,
    "contexto_registral": SECTION_REGISTRAL,
    "proveedor_adjudicado": SECTION_WINNER,
    "relacion_entidad_proveedor": SECTION_RELATION,
    "contexto_comparativo": SECTION_CONTEXT,
}
_ID = Field(max_length=64)


class LLMPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_signal_order: list[str] = Field(default_factory=list, max_length=12)
    que_se_contrato: list[str] = Field(default_factory=list, max_length=12)
    senales_detectadas: list[str] = Field(default_factory=list, max_length=14)
    contexto_registral: list[str] = Field(default_factory=list, max_length=6)
    proveedor_adjudicado: list[str] = Field(default_factory=list, max_length=8)
    relacion_entidad_proveedor: list[str] = Field(default_factory=list, max_length=4)
    contexto_comparativo: list[str] = Field(default_factory=list, max_length=6)
    reviewer_note: str | None = Field(default=None, max_length=32)

    def to_render_plan(self) -> RenderPlan:
        return RenderPlan(
            sections={title: getattr(self, key) for key, title in SECTION_KEYS.items()},
            summary_signal_order=self.summary_signal_order,
            reviewer_note=self.reviewer_note,
        )
