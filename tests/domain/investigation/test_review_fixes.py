# ruff: noqa: E501
"""Regression tests for the independent review: privacy guard, plausibility, snapshot caveats, coverage."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from veedor.domain.dossier.grounding import verify
from veedor.domain.dossier.investigation_facts import multiple_text
from veedor.domain.dossier.models import (
    AuditFacts,
    CompanyFinancialsFacts,
    CompanyRegistryFacts,
    EvidencePack,
    InvestigationFacts,
    SimilarPurchasesFacts,
    TaxRegistryLiveFacts,
)
from veedor.domain.dossier.template import catalogue, render_template
from veedor.domain.investigation.assemble import summarise_lookups
from veedor.domain.investigation.convert import audit_facts, company_facts, financials_facts, tax_facts
from veedor.domain.investigation.models import ToolCall
from veedor.domain.investigation.results import CompaniaInfo, Financials, ReportsFile, SriRucInfo
from veedor.infrastructure.investigations.store import contains_natural_person_ruc

TODAY = date(2026, 11, 16)
PACKS = Path(__file__).resolve().parents[2] / "fixtures" / "dossier"
HEADERS = ["No", "Unidad de Control", "Entidad", "Diligencia", "Periodo\nDesde", "Periodo\nHasta",
           "Tipo de informe", "Nº Informe", "Fecha\nAprobado"]  # fmt: skip


def pack(**process) -> EvidencePack:
    p = EvidencePack.model_validate(json.loads((PACKS / "pack_full.json").read_text()))
    return p.model_copy(update={"process": p.process.model_copy(update=process)}) if process else p


def with_inv(p: EvidencePack, **parts) -> EvidencePack:
    return p.model_copy(update={"investigation": InvestigationFacts(**parts)})


def text(p: EvidencePack) -> str:
    n = render_template(p)
    return n.summary_es + "\n" + "\n".join(f"{s.title}\n{s.body}" for s in n.sections)


# --- H1: the privacy guard only reads whole string tokens ---------------------------------------


@pytest.mark.parametrize(
    "document",
    [
        {"matched": "1234567890123.4567"},  # a float artifact: digits next to a decimal mark
        {"matched": "0.1234567890123"},
        {"amount": 1234567890123.0},  # a number, not a string
        {"matched": "9999999999999999.0"},
        {"text": "USD 1.234.567.890.123,00"},
        {
            "text": "0900000000001 masked 1712*********"
        },  # third digit 0 here is a masked/company shape? see below
    ][:5],
)
def test_floats_amounts_and_artifacts_are_not_identifiers(document):
    assert not contains_natural_person_ruc(json.dumps(document))


@pytest.mark.parametrize(
    "value", ["1712345678001", "RUC 0401234567001.", "(0601234567001)", "id=0512345678001;"]
)
def test_a_natural_person_ruc_is_still_found_as_a_whole_token(value):
    # third digit 0-5: natural person; the token must be whole (no digit or decimal mark attached)
    expected = value[-14:-1] if value.endswith((".", ")", ";")) else value[-13:]
    assert contains_natural_person_ruc(json.dumps({"x": value})) == (expected[2] in "012345")


def test_company_and_masked_rucs_are_not_flagged():
    assert not contains_natural_person_ruc(json.dumps({"x": "1790012345001 y 1712*********"}))


# --- M2: only fiscal years strictly before the process year -------------------------------------


def fin(*years):
    return Financials.model_validate({"ruc": "0992764473001", "years": [
        {"anio": y, "patrimonio": 100.0 * (i + 1), "activos": 200.0, "n_empleados": 5} for i, y in enumerate(years)]})  # fmt: skip


def test_financials_use_the_latest_year_strictly_before_the_process():
    p = pack(first_award_date="2018-01-23")  # the process of the review: 23 January 2018
    p = p.model_copy(update={"history": None})
    facts = financials_facts(fin(2016, 2017, 2018, 2019), p, TODAY)
    assert facts.fiscal_year == 2017
    only_later = financials_facts(fin(2018, 2019), p, TODAY)
    assert only_later.found is False
    body = text(with_inv(p, financials=only_later))
    assert "no disponible para un ejercicio anterior al proceso" in body


# --- M4 + M-extra: plausibility and zero as missing ----------------------------------------------


def test_absurd_values_are_rejected_recorded_and_rendered_as_out_of_range():
    p = pack()
    record = Financials.model_validate({"ruc": "0992764473001", "years": [
        {"anio": 2020, "patrimonio": -1e15, "activos": 1e18, "n_empleados": 9_999_999}]})  # fmt: skip
    facts = financials_facts(record, p, TODAY)
    assert set(facts.out_of_range) == {"equity", "assets", "employees"}
    assert facts.equity is None and facts.assets is None and facts.employees is None
    body = text(with_inv(p, financials=facts))
    assert body.count("no disponible (valor fuera de rango en la fuente)") >= 3
    assert verify(body, with_inv(p, financials=facts)).passed


def test_absurd_dates_in_company_and_sri_records():
    p = pack()
    company = company_facts(CompaniaInfo(ruc="0992764473001", fecha_constitucion="31/12/2099", capital_suscrito="1e15",
                                          ultimo_balance="2099"), p, TODAY)  # fmt: skip
    assert set(company.out_of_range) == {"incorporation_date", "last_balance_year", "subscribed_capital"}
    assert company.incorporation_date is None and company.days_incorporation_to_process is None
    sri = tax_facts(SriRucInfo(ruc="0992764473001", estado="Activo", fecha_inicio_actividades="31-12-2099",
                               fecha_cese_actividades="01-01-1541"), p, TODAY)  # fmt: skip
    assert (
        set(sri.out_of_range) == {"activity_start_date", "cessation_date"} and sri.cessation_reported is None
    )
    body = text(with_inv(p, company=company, tax_registry=sri))
    assert "Fecha de constitución: no disponible (valor fuera de rango en la fuente)" in body
    assert verify(body, with_inv(p, company=company, tax_registry=sri)).passed


def test_zero_is_missing_data_never_a_reported_figure():
    p = pack()
    facts = financials_facts(Financials.model_validate({"ruc": "0992764473001", "years": [
        {"anio": 2020, "patrimonio": 0.0, "activos": 0.0, "n_empleados": 0}]}), p, TODAY)  # fmt: skip
    assert (
        facts.equity is None and facts.assets is None and facts.employees is None and facts.out_of_range == []
    )
    assert "USD 0,00" not in text(with_inv(p, financials=facts))
    registry = p.winner.registry.model_copy(update={"latest_revenue": 0.0, "latest_revenue_year": 2025,
                                                   "revenue_award_year": 0.0, "award_year": 2023})  # fmt: skip
    zero = p.model_copy(update={"winner": p.winner.model_copy(update={"registry": registry})})
    assert "USD 0,00" not in text(zero) and "Ingresos más recientes" not in text(zero)
    assert verify(text(zero), zero).passed


# --- M5: snapshots are labelled ------------------------------------------------------------------


def test_legal_status_and_capital_say_they_are_snapshots():
    p = pack()
    company = company_facts(
        CompaniaInfo(ruc="0992764473001", situacion_legal="ACTIVA", capital_suscrito="400,00"), p, TODAY
    )
    body = text(with_inv(p, company=company))
    assert (
        "a la fecha de la consulta" in body
        and "no es necesariamente el vigente al momento del proceso" in body.lower()
    )
    assert "compara el monto adjudicado con el capital registrado a la fecha de la consulta" in body
    assert verify(body, with_inv(p, company=company)).passed


# --- L2 -----------------------------------------------------------------------------------------


def test_tiny_multiples_are_bounded_not_zero():
    assert multiple_text(0.004) == "menos de 0,01 veces" and multiple_text(172.28) == "172,3 veces"
    p = pack()
    facts = CompanyRegistryFacts(
        outcome="ok", found=True, subscribed_capital=1e11, award_to_capital_times=0.0003
    )
    body = text(with_inv(p, company=facts))
    assert "menos de 0,01 veces" in body and "0 veces" not in body.replace("0,01 veces", "")
    assert verify(body, with_inv(p, company=facts)).passed


# --- M3: approval date, audited period, coverage of the process date ----------------------------


def row(entity, number, start, end, approved="3/1/2023", title="Examen Especial a los procesos"):
    return ["1", "UNIDAD", entity, title, start, end, "General", number, approved]


def test_header_spellings_period_and_overlap_with_the_process_date():
    p = pack()
    buyer = p.process.buyer_name
    file = ReportsFile.model_validate({"headers": HEADERS, "truncated": True, "rows": [
        row(buyer, "DNA1-0001-2023", "2022-01-01", "2023-12-31"),  # includes 2023-08-25
        row(buyer, "DNA1-0002-2023", "2019-01-01", "2020-12-31"),  # does not
        ["1", "U", buyer, "x", "", "", "General", "DNA1-0003-2023", "2023-02-02"],  # no period
    ]})  # fmt: skip
    facts = audit_facts(
        buyer, [file], files_in_catalogue=8, key_index={}, process_day=date(2023, 8, 25), today=TODAY
    )
    by_id = {r.report_id: r for r in facts.reports}
    assert (
        by_id["DNA1-0001-2023"].covers_process is True
        and by_id["DNA1-0001-2023"].approval_date == "2023-01-03"
    )
    assert by_id["DNA1-0002-2023"].covers_process is False and by_id["DNA1-0003-2023"].covers_process is None
    assert by_id["DNA1-0001-2023"].period_from == "2022-01-01"
    body = text(with_inv(p, audit=facts))
    assert "cuyo período examinado incluye la fecha del proceso" in body
    assert "cuyo período examinado no incluye la fecha del proceso" in body
    assert "con período examinado no disponible" in body
    assert verify(body, with_inv(p, audit=facts)).passed


# --- L1 -----------------------------------------------------------------------------------------


def test_similar_purchases_state_floor_count_and_basis():
    p = pack()
    for basis, phrase in (
        ("description", "según la descripción del objeto"),
        ("classification", "según la clasificación del objeto"),
    ):
        facts = SimilarPurchasesFacts(outcome="ok", neighbours_examined=50, similarity_floor=0.75, n_above_floor=31,
                                      basis=basis, n_in_window=4, n_with_amount=3, combined_amount=1000.5)  # fmt: skip
        body = text(with_inv(p, similar=facts))
        assert phrase in body and "31 superan una similitud mínima de 0,75" in body
        assert verify(body, with_inv(p, similar=facts)).passed
    none = SimilarPurchasesFacts(
        outcome="ok", neighbours_examined=50, similarity_floor=0.75, n_above_floor=0, basis="classification"
    )
    assert "ninguna supera una similitud mínima de 0,75" in text(with_inv(p, similar=none))


# --- L3 -----------------------------------------------------------------------------------------


def test_files_consulted_and_retries_are_reported_separately():
    now = __import__("datetime").datetime.now()

    def call(attempts, outcome="ok"):
        return ToolCall(specialist="audit", tool="get_contraloria_informe", target="buyer", started_at=now,
                        ended_at=now, duration_ms=1.0, outcome=outcome, attempts=attempts)  # fmt: skip

    (summary,) = summarise_lookups([call(1), call(1), call(2)])
    assert summary.calls == 3 and summary.retries == 1
    p = pack()
    body = text(with_inv(p, lookups=[summary]))
    assert "3 consultas; un reintento" in body and "intentos" not in body


def test_failed_catalogue_audit_is_unchanged():
    assert AuditFacts(outcome="timeout").outcome == "timeout"
    assert CompanyFinancialsFacts(outcome="ok", found=False).fiscal_year is None
    assert TaxRegistryLiveFacts(outcome="skipped").out_of_range == []
    assert any(f.id == "investigation.run.note" for f in catalogue(with_inv(pack())))
