"""Dossier data model: the evidence pack, the generated dossier and the grounding report.

Every value that a dossier may state about a process lives in an `EvidencePack`. Dates are ISO
``YYYY-MM-DD`` strings (local date of the source timestamp). Natural persons are already masked
inside the pack (name ``"Persona natural"``, RUC first four digits plus nine asterisks), so no
text generated from a pack can reveal them.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, computed_field

if TYPE_CHECKING:
    from veedor.domain.dossier.allowed import AllowedValues


class Source(BaseModel):
    dataset: str
    licence: str | None = None
    retrieved_at: str | None = None
    record_id: str | None = None
    url: str | None = None
    note: str | None = None


class SignalFact(BaseModel):
    code: str
    label_es: str
    value: float | None = None
    threshold: float | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    caveat: str | None = None


class ProcessFacts(BaseModel):
    ocid: str
    process_code: str | None = None
    year: int | None = None
    buyer_ruc: str | None = None
    buyer_name: str | None = None
    buyer_region: str | None = None
    buyer_locality: str | None = None
    method: str | None = None
    method_group: str | None = None
    category: str | None = None
    status: str | None = None
    budget: float | None = None
    award_total: float | None = None
    award_budget_ratio: float | None = None  # derived by the reader: award_total / budget
    n_tenderers: int | None = None
    n_awards: int | None = None
    tender_start: str | None = None
    tender_end: str | None = None
    first_award_date: str | None = None
    date_signed: str | None = None
    main_cpc: str | None = None
    main_cpc_description: str | None = None


class RegistryFacts(BaseModel):
    """Registry facts about the winner. ``None`` means unknown / dataset not available."""

    status: str | None = None
    taxpayer_type: str | None = None
    activity_start_date: str | None = None
    suspension_date: str | None = None
    restart_date: str | None = None
    ciiu_code: str | None = None
    activity: str | None = None
    province: str | None = None
    legal_name: str | None = None
    ghost_listed: bool | None = None
    company_type: str | None = None
    latest_revenue: float | None = None
    latest_revenue_year: int | None = None
    award_year: int | None = None  # year of the process reference date
    revenue_award_year: float | None = None  # revenue reported for `award_year`, if any


class WinnerFacts(BaseModel):
    ruc: str | None = None
    name: str | None = None
    kind: str = "unknown"
    n_award_suppliers: int = 1
    registry: RegistryFacts = Field(default_factory=RegistryFacts)


class HistoryFacts(BaseModel):
    """Awards from the same buyer to the same supplier, relative to the process reference date.

    The reference date is the same fallback the signals use: first award date, else signature date,
    else start of tenders, else publication date (`reference_date_kind` names which one).
    """

    reference_date: str
    reference_date_kind: str
    n_previous_awards: int
    n_with_amount: int
    total_previous_amount: float | None = None
    first_award_date: str | None = None
    last_award_date: str | None = None
    n_pair_awards: int = 0  # every award of the pair in the dataset, including this process
    pair_first_year: int | None = None
    pair_last_year: int | None = None


class ComparisonStats(BaseModel):
    """Statistics of all processes with the same method and year."""

    method: str | None = None
    year: int | None = None
    n_processes: int | None = None
    median_tenderers: float | None = None
    single_bidder_share: float | None = None  # fraction 0-1
    median_award_budget_ratio: float | None = None  # fraction


class EvidencePack(BaseModel):
    process: ProcessFacts
    signals_available: bool = True
    signals: list[SignalFact] = Field(default_factory=list)
    risk_score: float | None = None
    winner: WinnerFacts | None = None
    history: HistoryFacts | None = None
    comparison: ComparisonStats | None = None
    sources: list[Source] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def n_signals(self) -> int:
        return len(self.signals)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def n_risk_signals(self) -> int:
        from veedor.domain.dossier.signal_text import is_informational

        return sum(1 for s in self.signals if not is_informational(s))

    def allowed_values(self) -> AllowedValues:
        """Flat set of numbers, dates, RUCs, codes and names that generated text may contain."""
        from veedor.domain.dossier.allowed import collect_allowed
        from veedor.domain.dossier.bindings import build_bindings, build_noun_bindings, build_role_bindings
        from veedor.domain.dossier.signal_text import is_informational

        allowed = collect_allowed(self.model_dump(mode="python"))
        allowed.bindings = build_bindings(self)
        allowed.nouns = build_noun_bindings(self)
        allowed.roles = build_role_bindings(self)
        allowed.claims = {
            "single_bidder": self.process.n_tenderers == 1,
            "n_risk_signals": sum(1 for s in self.signals if not is_informational(s)),
            "n_previous_awards": self.history.n_previous_awards if self.history else None,
        }
        return allowed


class Section(BaseModel):
    title: str
    body: str


class GroundedToken(BaseModel):
    kind: Literal["number", "percent", "date", "ruc", "code", "name", "quote", "forbidden"]
    text: str
    start: int
    end: int
    matched: str | None = None
    reason: str | None = None


class GroundingReport(BaseModel):
    passed: bool
    n_checked: int
    supported: list[GroundedToken] = Field(default_factory=list)
    unsupported: list[GroundedToken] = Field(default_factory=list)
    forbidden: list[GroundedToken] = Field(default_factory=list)


class Dossier(BaseModel):
    ocid: str
    generated_at: datetime
    mode: Literal["template", "template_minimal", "llm"]
    summary_es: str
    sections: list[Section]
    sources: list[Source]
    grounding_report: GroundingReport
    llm_attempts: int = 0
    renderer_version: int = 0  # 0 = written before versioning; see domain/dossier/version.py
    fallback_reason: str | None = None

    def full_text(self) -> str:
        return "\n".join([self.summary_es, *[f"{s.title}\n{s.body}" for s in self.sections]])
