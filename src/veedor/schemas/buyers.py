"""Buyer endpoint schemas."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

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
