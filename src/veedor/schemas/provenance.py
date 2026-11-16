"""Provenance of the facts shown on a process page."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from veedor.schemas.common import MaskedModel


class ProvenanceSource(BaseModel):
    id: str = Field(examples=["sercop_ocds"])
    name: str
    publisher: str
    licence: str
    retrieved_at: str | None = Field(None, description="Fecha de obtención registrada (AAAA-MM-DD).")
    url: str | None = None


class ProvenanceFact(BaseModel):
    key: str = Field(examples=["facts.budget"])
    label_es: str
    value: Any = Field(
        None, description="Valor mostrado en la página, con la misma máscara de personas naturales."
    )
    source_id: str
    source_field: str | None = Field(None, description="Ruta OCDS o archivo y columna del registro.")
    derived: bool = False
    derivation_es: str | None = None
    verify_es: str


class ProcessProvenance(MaskedModel):
    mask_whole_payload: ClassVar[bool] = True

    ocid: str
    sources: list[ProvenanceSource]
    facts: list[ProvenanceFact]
