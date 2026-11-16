"""Turn validated tool results into typed facts (pure).

Only declared, validated fields cross this boundary, and each is either a number, a date, a flag or a
member of a closed vocabulary. The one exception is a Contraloría report title: it is screened,
length-capped and kept as an attributed quotation that the model never sees.
"""

from __future__ import annotations

import re
from datetime import date

from veedor.domain.dossier.models import (
    AuditFacts,
    AuditReportRef,
    CompanyFinancialsFacts,
    CompanyRegistryFacts,
    EvidencePack,
    TaxRegistryLiveFacts,
)
from veedor.domain.dossier.safety import is_unsafe_text
from veedor.domain.dossier.text import canonical
from veedor.domain.investigation import bounds, vocab
from veedor.domain.investigation.entity_match import canonical_entity_key, is_ambiguous
from veedor.domain.investigation.policies import MAX_REPORT_FILES
from veedor.domain.investigation.results import (
    REPORT_ID_PATTERN,
    Catalogue,
    CompaniaInfo,
    Financials,
    ReportsFile,
    SriRucInfo,
    parse_amount,
    parse_day,
    parse_year,
)
from veedor.domain.masking import safe_free_text

MAX_TITLE_CHARS = 300
MAX_LISTED_REPORTS = 6


def reference_date(pack: EvidencePack) -> date | None:
    """The process date every "days between" figure uses: the same fallback as the history facts."""
    if pack.history is not None:
        return parse_day(pack.history.reference_date)
    p = pack.process
    for value in (p.first_award_date, p.date_signed, p.tender_start):
        parsed = parse_day(value)
        if parsed is not None:
            return parsed
    return None


def company_facts(record: CompaniaInfo, pack: EvidencePack, today: date) -> CompanyRegistryFacts:
    rejected: list[str] = []
    incorporation = bounds.day("incorporation_date", parse_day(record.fecha_constitucion), today, rejected)
    reference = reference_date(pack)
    days = (reference - incorporation).days if incorporation and reference else None
    capital = bounds.amount("subscribed_capital", parse_amount(record.capital_suscrito), rejected)
    total = pack.process.award_total
    times = round(total / capital, 4) if capital and total is not None else None
    return CompanyRegistryFacts(
        outcome="ok",
        found=True,
        incorporation_date=incorporation.isoformat() if incorporation else None,
        days_incorporation_to_process=days,
        subscribed_capital=capital,
        award_to_capital_times=times,
        legal_status=vocab.legal_status(record.situacion_legal),
        last_balance_year=bounds.year(
            "last_balance_year", parse_year(record.ultimo_balance), today, rejected
        ),
        out_of_range=rejected,
    )


def financials_facts(record: Financials, pack: EvidencePack, today: date) -> CompanyFinancialsFacts:
    """Figures of the latest fiscal year strictly before the process year (later data was not known)."""
    reference = reference_date(pack)
    year = reference.year if reference else pack.process.year
    earlier = [y for y in record.years if year is not None and y.anio < year]
    if not earlier:
        return CompanyFinancialsFacts(outcome="ok", found=False)
    latest = max(earlier, key=lambda y: y.anio)
    rejected: list[str] = []
    return CompanyFinancialsFacts(
        outcome="ok",
        found=True,
        fiscal_year=latest.anio,
        employees=bounds.count("employees", latest.n_empleados, rejected),
        equity=bounds.amount("equity", latest.patrimonio, rejected, allow_negative=True),
        assets=bounds.amount("assets", latest.activos, rejected),
        out_of_range=rejected,
    )


def tax_facts(record: SriRucInfo, pack: EvidencePack, today: date) -> TaxRegistryLiveFacts:
    rejected: list[str] = []
    live = vocab.sri_status(record.estado)
    downloaded = vocab.sri_status(pack.winner.registry.status) if pack.winner else None
    start = bounds.day("activity_start_date", parse_day(record.fecha_inicio_actividades), today, rejected)
    cessation_text = (record.fecha_cese_actividades or "").strip()
    cessation = (
        bounds.day("cessation_date", parse_day(cessation_text), today, rejected) if cessation_text else None
    )
    return TaxRegistryLiveFacts(
        outcome="ok",
        found=True,
        status=live,
        taxpayer_class=vocab.taxpayer_class(record.clase_contribuyente),  # type: ignore[arg-type]
        mipymes=vocab.mipymes(record.categoria_mipymes),  # type: ignore[arg-type]
        activity_start_date=start.isoformat() if start else None,
        cessation_reported=True if cessation else (None if cessation_text else False),
        status_matches_download=None if live is None or downloaded is None else live == downloaded,
        out_of_range=rejected,
    )


# --- Contraloría -------------------------------------------------------------------------------

_REPORT_LABEL = re.compile(r"^informes aprobados\b")


def report_file_ids(catalogue: Catalogue) -> tuple[list[str], int]:
    """Ids of the approved-report files the audit specialist may read, and how many the catalogue lists.

    Only entries whose label opens with "Informes aprobados" qualify (the catalogue also lists a
    glossary and other documents). The most recent approval periods come first when the labels carry a
    year; otherwise the catalogue order is kept. The id is validated by the result model's pattern.
    """
    eligible = [e for e in catalogue.informes if _REPORT_LABEL.match(canonical(e.label))]

    def year_of(label: str) -> int:
        years = re.findall(r"\b(20\d{2})\b", label)
        return int(years[-1]) if years else 0

    ordered = sorted(eligible, key=lambda e: (-year_of(e.label), -int(e.id)))
    return [e.id for e in ordered[:MAX_REPORT_FILES]], len(eligible)


def _column(headers: list[str], *names: str) -> int | None:
    folded = [" ".join(re.sub(r"[^a-z0-9 ]+", " ", canonical(h)).split()) for h in headers]
    for name in names:
        if name in folded:
            return folded.index(name)
    return None


def _cell(row: list, index: int | None) -> str | None:
    if index is None or index >= len(row) or row[index] is None:
        return None
    return " ".join(str(row[index]).split()) or None


def has_report_columns(headers: list[str]) -> bool:
    return _column(headers, "entidad") is not None and _column(headers, "diligencia") is not None


def _in_range(value: date | None, today: date) -> date | None:
    return value if value is not None and bounds.DATE_MIN <= value <= today else None


def _reference_of(
    row: list, cols: dict[str, int | None], process_day: date | None, today: date
) -> AuditReportRef:
    raw_id = _cell(row, cols["id"])
    report_id = raw_id if raw_id and REPORT_ID_PATTERN.match(raw_id) else None
    approved = _in_range(parse_day(_cell(row, cols["date"])), today)
    start = _in_range(parse_day(_cell(row, cols["from"])), today)
    end = _in_range(parse_day(_cell(row, cols["to"])), today)
    covers = None
    if start and end and process_day and start <= end:
        covers = start <= process_day <= end
    title = _cell(row, cols["title"])
    if title:
        title = title[:MAX_TITLE_CHARS]
        title, _withheld = safe_free_text(title)
        if title and is_unsafe_text(title):
            title = None
    return AuditReportRef(
        report_id=report_id,
        report_type=vocab.report_type(_cell(row, cols["type"])),
        approval_date=approved.isoformat() if approved else None,
        period_from=start.isoformat() if start else None,
        period_to=end.isoformat() if end else None,
        covers_process=covers,
        title=title,
    )


def audit_facts(
    buyer_name: str | None,
    files: list[ReportsFile],
    *,
    files_in_catalogue: int,
    key_index: dict[str, frozenset[str]] | None,
    process_day: date | None = None,
    today: date | None = None,
) -> AuditFacts:
    """Reports whose audited entity has the buyer's canonical key, with an honest coverage statement.

    The server returns at most a fixed number of rows per file and flags the preview as truncated, so
    a search can confirm a report but never rule one out: `conclusive` is True only when matching is
    reliable and every row of every catalogue file was read.
    """
    today = today or date.today()
    key = canonical_entity_key(buyer_name)
    reliable = key is not None and key_index is not None and not is_ambiguous(key, key_index)
    examined_rows, matches, seen = 0, [], set()
    complete = files_in_catalogue > 0 and len(files) == files_in_catalogue
    for file in files:
        cols = {
            "entity": _column(file.headers, "entidad"),
            "title": _column(file.headers, "diligencia"),
            "type": _column(file.headers, "tipo de informe"),
            "id": _column(file.headers, "no informe", "n informe", "numero informe"),
            "date": _column(file.headers, "fecha aprobacion", "fecha aprobado", "fecha de aprobacion"),
            "from": _column(file.headers, "periodo desde", "periodo inicio"),
            "to": _column(file.headers, "periodo hasta", "periodo fin"),
        }
        complete = complete and file.truncated is False
        for row in file.rows:
            examined_rows += 1
            if not reliable or canonical_entity_key(_cell(row, cols["entity"])) != key:
                continue
            ref = _reference_of(row, cols, process_day, today)
            identity = ref.report_id or (ref.title, ref.approval_date)
            if identity not in seen:
                seen.add(identity)
                matches.append(ref)
    return AuditFacts(
        outcome="ok",
        conclusive=bool(reliable and complete),
        match_reliable=reliable,
        files_examined=len(files),
        files_in_catalogue=files_in_catalogue,
        rows_examined=examined_rows,
        coverage_complete=complete,
        n_reports=len(matches) if reliable else None,
        reports=matches[:MAX_LISTED_REPORTS],
    )
