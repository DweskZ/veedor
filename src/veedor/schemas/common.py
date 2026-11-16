"""Shared API schemas: masking base model, pagination envelope, error model."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from veedor.domain.masking import PartyFields, mask_fields, mask_payload


class MaskedModel(BaseModel):
    """Base for every response model that may carry supplier or buyer identities.

    Masking runs in a `before` validator, so no instance of a subclass can hold the real name or
    full RUC of a natural person, whichever endpoint builds it.
    """

    model_config = ConfigDict(extra="ignore")

    party_fields: ClassVar[tuple[PartyFields, ...]] = ()
    payload_fields: ClassVar[tuple[str, ...]] = ()
    mask_whole_payload: ClassVar[bool] = False

    @model_validator(mode="before")
    @classmethod
    def _apply_masking(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = {
            key: value.isoformat() if isinstance(value, (date, datetime)) else value
            for key, value in data.items()
        }
        out = mask_fields(out, cls.party_fields)
        if cls.mask_whole_payload:
            return mask_payload(out, honorifics=False)  # the use case already applied the full rule
        return out

    @model_validator(mode="after")
    def _mask_payload_fields(self) -> Self:
        """Runs after parsing, so JSON-string fields are already structured when masked."""
        for field in self.payload_fields:
            setattr(self, field, mask_payload(getattr(self, field)))
        return self


class Party(MaskedModel):
    """A supplier or buyer identity, masked when it is a natural person."""

    party_fields: ClassVar[tuple[PartyFields, ...]] = (("ruc", "name", "kind"),)

    ruc: str | None = Field(None, examples=["1790012345001"])
    name: str | None = Field(None, examples=["Constructora Andina S.A."])
    kind: str = Field("unknown", description="natural_person | company | public_entity | other | unknown")


class Page[T](BaseModel):
    items: list[T]
    page: int = Field(examples=[1])
    page_size: int = Field(examples=[25])
    total: int = Field(examples=[123])


class ErrorBody(BaseModel):
    code: str = Field(examples=["data_unavailable"])
    message: str = Field(examples=["Los datos requeridos no están disponibles todavía."])
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
