"""Buyer endpoint schemas."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from veedor.domain.masking import PartyFields
from veedor.schemas.common import MaskedModel


class BuyerSupplier(MaskedModel):
    party_fields: ClassVar[tuple[PartyFields, ...]] = (("ruc", "name", "kind"),)

    ruc: str | None = None
    name: str | None = None
    kind: str = "unknown"
    n_awards: int
    total_awarded: float | None = None
    share_of_awarded: float | None = None
    mean_risk_score: float | None = None


class SignalCount(BaseModel):
    code: str
    label_es: str | None = None
    kind: str | None = None
    count: int


class BuyerDetail(MaskedModel):
    party_fields: ClassVar[tuple[PartyFields, ...]] = (("ruc", "name", None),)

    ruc: str
    name: str | None = None
    n_processes: int
    n_flagged: int
    total_awarded: float | None = None
    mean_risk_score: float | None = None
    first_year: int | None = None
    last_year: int | None = None
    top_suppliers: list[BuyerSupplier]
    signal_mix: list[SignalCount]


class BuyerHit(MaskedModel):
    party_fields: ClassVar[tuple[PartyFields, ...]] = (("ruc", "name", None),)

    ruc: str = Field(description="RUC de 13 dígitos de la entidad contratante.", examples=["1760001230001"])
    name: str = Field(
        description="Nombre más frecuente de la entidad.", examples=["GAD Municipal de Ejemplo"]
    )
    region_label: str = Field(
        description="Provincia más frecuente de la entidad, o 'Sin provincia registrada'.",
        examples=["Pichincha"],
    )
    processes_total: int = Field(description="Procesos de la entidad en los datos.", examples=[312])


class BuyerSearchResult(BaseModel):
    items: list[BuyerHit] = Field(
        description="Hasta 10 entidades; primero las que empiezan con el texto, luego las que lo "
        "tienen al inicio de una palabra, luego el resto, y a igual calidad las de más procesos."
    )
