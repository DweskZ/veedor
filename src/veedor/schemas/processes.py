"""Process endpoint schemas."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator

from veedor.domain.masking import PartyFields, mask_free_text, safe_free_text
from veedor.schemas.common import MaskedModel, Party
from veedor.schemas.profile import SupplierProfile

NOTICE_ES = (
    "Los indicadores son señales de riesgo calculadas a partir de datos públicos. "
    "No constituyen una acusación."
)


class ProcessSummary(MaskedModel):
    """One row of `process_scores`."""

    party_fields: ClassVar[tuple[PartyFields, ...]] = (
        ("winner_ruc", "winner_name", "winner_kind"),
        ("buyer_ruc", "buyer_name", None),
    )

    ocid: str = Field(examples=["ocds-5wno2w-LICO-GADM-2023-0001"])
    risk_score: float = Field(examples=[42.5])
    n_signals: int = Field(examples=[2])
    signal_codes: list[str] = Field(examples=[["SINGLE_BIDDER", "LOW_SAVING"]])
    n_context_signals: int = Field(0, description="Number of context signals (not part of the score).")
    context_signal_codes: list[str] = Field(default_factory=list, examples=[["GHOST_COMPANY_LISTED_LATER"]])
    anomaly_score: float | None = None
    award_total: float | None = None
    year: int | None = None
    buyer_ruc: str | None = None
    buyer_name: str | None = None
    method: str | None = None
    winner_ruc: str | None = None
    winner_name: str | None = None
    winner_kind: str | None = None

    @field_validator("signal_codes", "context_signal_codes", mode="before")
    @classmethod
    def _none_to_empty(cls, value: Any) -> Any:
        return [] if value is None else value

    @field_validator("n_context_signals", mode="before")
    @classmethod
    def _none_to_zero(cls, value: Any) -> Any:
        return 0 if value is None else value


class FiredSignal(MaskedModel):
    payload_fields: ClassVar[tuple[str, ...]] = ("evidence",)

    code: str = Field(examples=["SINGLE_BIDDER"])
    label_es: str | None = Field(None, examples=["Oferente único"])
    kind: str = Field("risk", description="risk | context. Context signals are not part of the score.")
    value: float | None = None
    threshold: float | None = None
    evidence: dict[str, Any] = Field(default_factory=dict, description="Parsed `evidence_json`.")

    @field_validator("evidence", mode="before")
    @classmethod
    def _parse_evidence(cls, value: Any) -> Any:
        if value is None or value == "":
            return {}
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return {}
        return value if isinstance(value, dict) else {"value": value}


class ProcessFacts(MaskedModel):
    party_fields: ClassVar[tuple[PartyFields, ...]] = (("buyer_ruc", "buyer_name", None),)

    @model_validator(mode="before")
    @classmethod
    def _guard_free_text(cls, data: Any) -> Any:
        """Safety net: free text is withheld when it holds a personal identifier, whatever the caller did."""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        out["description"], out["description_withheld"] = safe_free_text(
            out.get("description"), withhold=bool(out.get("description_withheld"))
        )
        if isinstance(out.get("main_cpc_description"), str):
            out["main_cpc_description"] = mask_free_text(out["main_cpc_description"])
        return out

    process_code: str | None = None
    release_date: str | None = None
    year: int | None = None
    buyer_ruc: str | None = None
    buyer_name: str | None = None
    buyer_region: str | None = None
    buyer_locality: str | None = None
    method: str | None = None
    method_group: str | None = None
    category: str | None = None
    status: str | None = None
    description: str | None = Field(None, description="None when withheld (see description_withheld).")
    description_withheld: bool = Field(
        False, description="True when the description was withheld to protect personal data."
    )
    budget: float | None = None
    tender_start: str | None = None
    tender_end: str | None = None
    n_tenderers: int | None = None
    n_bids: int | None = None
    n_awards: int | None = None
    award_total: float | None = None
    first_award_date: str | None = None
    date_signed: str | None = None
    main_cpc: str | None = None
    main_cpc_description: str | None = None


class Score(BaseModel):
    risk_score: float
    n_signals: int
    n_context_signals: int = 0
    context_signal_codes: list[str] = Field(default_factory=list)
    anomaly_score: float | None = None


class AwardOut(MaskedModel):
    party_fields: ClassVar[tuple[PartyFields, ...]] = (("supplier_ruc", "supplier_name", None),)

    award_id: str | None = None
    award_date: str | None = None
    supplier_ruc: str | None = None
    supplier_name: str | None = None
    amount: float | None = None


class ProcessDetail(BaseModel):
    ocid: str
    facts: ProcessFacts | None = Field(None, description="None when the process is not in the lake.")
    score: Score | None = Field(None, description="None when the process has no score row.")
    signals: list[FiredSignal]
    winner: SupplierProfile | None = None
    tenderers: list[Party]
    awards: list[AwardOut]
    notice_es: str = NOTICE_ES
