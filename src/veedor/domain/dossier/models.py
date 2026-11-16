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


LookupOutcome = Literal["ok", "timeout", "upstream_error", "invalid_result", "skipped"]
LegalStatus = Literal["active", "dissolution_or_liquidation", "cancelled_or_inactive", "other"]
SriStatus = Literal["active", "suspended", "cancelled", "other"]


class CompanyRegistryFacts(BaseModel):
    """Live Superintendencia de Compañías record of the winner. Never holds a person's name."""

    outcome: LookupOutcome = "skipped"
    found: bool | None = None  # False: the source answered that it has no record for this RUC
    incorporation_date: str | None = None
    days_incorporation_to_process: int | None = None  # negative when the process predates it
    subscribed_capital: float | None = None
    award_to_capital_times: float | None = None  # award_total / subscribed_capital
    legal_status: LegalStatus | None = None
    last_balance_year: int | None = None
    out_of_range: list[str] = Field(default_factory=list)  # fields whose source value was implausible


class CompanyFinancialsFacts(BaseModel):
    """Latest fiscal year at or before the process year that has a filed financial statement."""

    outcome: LookupOutcome = "skipped"
    found: bool | None = None
    fiscal_year: int | None = None
    employees: int | None = None
    equity: float | None = None
    assets: float | None = None
    out_of_range: list[str] = Field(default_factory=list)


class TaxRegistryLiveFacts(BaseModel):
    """Live SRI public record of the winner (registry fields only, no tax amounts)."""

    outcome: LookupOutcome = "skipped"
    found: bool | None = None
    status: SriStatus | None = None
    taxpayer_class: Literal["especial", "otro", "other"] | None = None
    mipymes: Literal["micro", "pequena", "mediana", "grande", "no_declarado", "other"] | None = None
    activity_start_date: str | None = None
    cessation_reported: bool | None = None
    status_matches_download: bool | None = None  # live status vs the downloaded SRI table
    out_of_range: list[str] = Field(default_factory=list)


class PairHistoryFacts(BaseModel):
    """Every other award between this buyer and this supplier, at any date."""

    outcome: LookupOutcome = "skipped"
    n_other_awards: int | None = None
    n_with_amount: int | None = None
    total_other_amount: float | None = None


class SimilarPurchasesFacts(BaseModel):
    """Same-buyer purchases among the nearest neighbours in the vector index, near the process date."""

    outcome: LookupOutcome = "skipped"
    window_days: int = 180
    neighbours_examined: int | None = None
    similarity_floor: float | None = None
    n_above_floor: int | None = None
    basis: Literal["description", "classification"] | None = None  # what the embeddings were made of
    n_in_window: int | None = None
    n_with_amount: int | None = None
    combined_amount: float | None = None


class AuditReportRef(BaseModel):
    report_id: str | None = None  # the report number as published (validated shape), else None
    report_type: str | None = None  # closed vocabulary only
    approval_date: str | None = None
    period_from: str | None = None
    period_to: str | None = None
    covers_process: bool | None = None  # does the audited period include the process date?
    title: str | None = None  # attributed quotation of the source, screened; never shown to a model


class AuditFacts(BaseModel):
    """Contraloría reports whose audited entity matches the buyer by a normalised-name comparison."""

    outcome: LookupOutcome = "skipped"
    conclusive: bool = False  # True only when matching was reliable and coverage was complete
    match_reliable: bool | None = None
    files_examined: int | None = None
    files_in_catalogue: int | None = None
    rows_examined: int | None = None
    coverage_complete: bool | None = None
    n_reports: int | None = None
    # Counts over ALL matches (the list below is capped): audited period includes / excludes the process
    # date / is not available. None in records written before the counts existed.
    n_listed: int | None = None  # how many of them are listed below (the cap)
    n_covering: int | None = None
    n_not_covering: int | None = None
    n_period_unknown: int | None = None
    reports: list[AuditReportRef] = Field(default_factory=list)  # capped, covering reports first


class SpecialistSummary(BaseModel):
    specialist: str  # closed vocabulary: company, tax_registry, history, audit
    n_tool_calls: int
    dispatches: int = 1


class LookupSummary(BaseModel):
    """One consulted source, aggregated from the tool log (no identifiers, no free text)."""

    source: str  # closed vocabulary, see `domain/investigation/vocab.py`
    outcome: LookupOutcome
    reason: str | None = None  # closed vocabulary
    calls: int = 1  # executed calls (several files of one source are several calls)
    retries: int = 0  # extra attempts after a failure, summed over the calls


class InvestigationFacts(BaseModel):
    company: CompanyRegistryFacts | None = None
    financials: CompanyFinancialsFacts | None = None
    tax_registry: TaxRegistryLiveFacts | None = None
    pair_history: PairHistoryFacts | None = None
    similar: SimilarPurchasesFacts | None = None
    audit: AuditFacts | None = None
    specialists: list[SpecialistSummary] = Field(default_factory=list)
    lookups: list[LookupSummary] = Field(default_factory=list)


class EvidencePack(BaseModel):
    process: ProcessFacts
    signals_available: bool = True
    signals: list[SignalFact] = Field(default_factory=list)
    risk_score: float | None = None
    winner: WinnerFacts | None = None
    history: HistoryFacts | None = None
    comparison: ComparisonStats | None = None
    investigation: InvestigationFacts | None = None
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
