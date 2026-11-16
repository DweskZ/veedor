"""Supplier profile shared by the process and supplier schemas."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer

from veedor.domain.masking import PartyFields
from veedor.schemas.common import MaskedModel


class SupplierProfile(MaskedModel):
    party_fields: ClassVar[tuple[PartyFields, ...]] = (("ruc", "name", "kind"),)

    ruc: str | None = Field(None, examples=["1790012345001"])
    name: str | None = Field(None, examples=["Constructora Andina S.A."])
    kind: str = "unknown"
    n_processes: int | None = None
    n_wins: int | None = None
    total_awarded: float | None = None
    first_award_date: str | None = None
    last_award_date: str | None = None
    n_buyers: int | None = None
    top_buyer_ruc: str | None = None
    top_buyer_share: float | None = None
    single_bidder_wins: int | None = None
    mean_risk_score: float | None = None

    @model_serializer(mode="wrap")
    def _label_only_for_persons(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Natural persons and unidentified parties expose no behavioural profile, only the label."""
        data = handler(self)
        if self.kind in {"natural_person", "unknown"}:
            return {key: data[key] for key in ("ruc", "name", "kind")}
        return data
