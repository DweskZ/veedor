"""Supplier endpoint schemas."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, field_validator

from veedor.domain.masking import PartyFields
from veedor.schemas.common import MaskedModel
from veedor.schemas.processes import ProcessSummary
from veedor.schemas.profile import SupplierProfile


class SriFacts(MaskedModel):
    party_fields: ClassVar[tuple[PartyFields, ...]] = (("ruc", "legal_name", None),)

    ruc: str | None = None
    legal_name: str | None = None
    status: str | None = None
    taxpayer_type: str | None = None
    activity_start_date: str | None = None
    suspension_date: str | None = None
    restart_date: str | None = None
    ciiu_code: str | None = None
    activity: str | None = None
    province: str | None = None


class SuperciasFacts(MaskedModel):
    party_fields: ClassVar[tuple[PartyFields, ...]] = (("ruc", "legal_name", None),)

    ruc: str | None = None
    expediente: str | None = None
    legal_name: str | None = None
    company_type: str | None = None
    province: str | None = None

    @field_validator("expediente", mode="before")
    @classmethod
    def _expediente_as_text(cls, value: object) -> object:
        """The registry stores the file number as an integer; expose it as text."""
        return None if value is None else str(value)


class FinancialYear(BaseModel):
    year: int
    revenue: float | None = None
    assets: float | None = None
    equity: float | None = None
    employees: float | None = None


class RegistryFacts(BaseModel):
    """Registry facts; a `None` section means the dataset or the record is not available."""

    sri: SriFacts | None = None
    ghost_company_listed: bool | None = Field(
        None, description="None when the SRI ghost-company dataset was not obtained."
    )
    supercias: SuperciasFacts | None = None
    financials: list[FinancialYear] = []


class SupplierDetail(BaseModel):
    profile: SupplierProfile
    registry: RegistryFacts
    recent_processes: list[ProcessSummary]
