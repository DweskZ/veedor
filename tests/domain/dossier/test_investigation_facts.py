# ruff: noqa: E501
"""Every investigation fact renders, verifies, and appears only where it applies."""

from __future__ import annotations

import pytest

from veedor.domain.dossier.grounding import verify
from veedor.domain.dossier.investigation_facts import FACT_SPECS, SPEC_BY_ID, UNTRUSTED_QUOTE_IDS
from veedor.domain.dossier.models import (
    AuditFacts,
    AuditReportRef,
    CompanyFinancialsFacts,
    CompanyRegistryFacts,
    InvestigationFacts,
    LookupSummary,
    PairHistoryFacts,
    SimilarPurchasesFacts,
    SpecialistSummary,
    TaxRegistryLiveFacts,
)
from veedor.domain.dossier.plan import PlanError, RenderPlan
from veedor.domain.dossier.template import catalogue, render_plan, render_template, validate_plan
from veedor.domain.dossier.vocabulary import SECTION_INVESTIGATION

OK = {"outcome": "ok", "found": True}


def investigated(pack, **parts):
    return pack.model_copy(update={"investigation": InvestigationFacts(**parts)})


def full(pack):
    return investigated(
        pack,
        company=CompanyRegistryFacts(**OK, incorporation_date="2023-06-01", days_incorporation_to_process=85,
                                     subscribed_capital=400.0, award_to_capital_times=61.225,
                                     legal_status="active", last_balance_year=2024),
        financials=CompanyFinancialsFacts(**OK, fiscal_year=2022, employees=7, equity=1234.5, assets=9999.0),
        tax_registry=TaxRegistryLiveFacts(**OK, status="active", taxpayer_class="otro", mipymes="micro",
                                          activity_start_date="2023-05-30", cessation_reported=False,
                                          status_matches_download=True),
        pair_history=PairHistoryFacts(outcome="ok", n_other_awards=3, n_with_amount=2, total_other_amount=5000.25),
        similar=SimilarPurchasesFacts(outcome="ok", neighbours_examined=50, n_in_window=4, n_with_amount=3,
                                      combined_amount=777.7),
        audit=AuditFacts(outcome="ok", match_reliable=True, files_examined=3, files_in_catalogue=8, rows_examined=600,
                         coverage_complete=False, n_reports=1,
                         reports=[AuditReportRef(report_id="DNA1-0001-2023", report_type="general",
                                                 approval_date="2023-01-03", title="Examen Especial a los procesos")]),
        specialists=[SpecialistSummary(specialist="company", n_tool_calls=2), SpecialistSummary(specialist="audit", n_tool_calls=1)],
        lookups=[LookupSummary(source="sri_live", outcome="upstream_error", reason="upstream_http_error", retries=1),
                 LookupSummary(source="contraloria_reports", outcome="ok")],
    )  # fmt: skip


def failed(pack):
    return investigated(
        pack,
        company=CompanyRegistryFacts(outcome="timeout"),
        financials=CompanyFinancialsFacts(outcome="timeout"),
        tax_registry=TaxRegistryLiveFacts(outcome="upstream_error"),
        pair_history=PairHistoryFacts(outcome="upstream_error"),
        similar=SimilarPurchasesFacts(outcome="upstream_error"),
        audit=AuditFacts(outcome="invalid_result"),
        specialists=[SpecialistSummary(specialist="history", n_tool_calls=1)],
        lookups=[LookupSummary(source="vector_index", outcome="skipped", reason="not_indexed", calls=1)],
    )


def conclusive_none(pack):
    return investigated(pack, audit=AuditFacts(outcome="ok", conclusive=True, match_reliable=True, files_examined=8,
                                               files_in_catalogue=8, rows_examined=100, coverage_complete=True, n_reports=0))  # fmt: skip


def unreliable_audit(pack):
    return investigated(pack, audit=AuditFacts(outcome="ok", match_reliable=False, files_examined=1, files_in_catalogue=1,
                                               rows_examined=5, coverage_complete=False))  # fmt: skip


def negative_days(pack):
    return investigated(
        pack,
        company=CompanyRegistryFacts(
            **OK, incorporation_date="2024-01-01", days_incorporation_to_process=-120
        ),
    )


def text(narrative) -> str:
    return narrative.summary_es + "\n" + "\n".join(f"{s.title}\n{s.body}" for s in narrative.sections)


def not_found(pack):
    return investigated(pack, company=CompanyRegistryFacts(outcome="ok", found=False),
                        financials=CompanyFinancialsFacts(outcome="ok", found=False),
                        tax_registry=TaxRegistryLiveFacts(outcome="ok", found=False))  # fmt: skip


BUILDERS = [full, failed, conclusive_none, unreliable_audit, negative_days, not_found]


@pytest.mark.parametrize("build", BUILDERS)
def test_every_applicable_fact_renders_and_the_whole_dossier_verifies(full_pack, build):
    pack = build(full_pack)
    report = verify(text(render_template(pack)), pack)
    assert report.passed, [t.model_dump() for t in report.unsupported + report.forbidden]


@pytest.mark.parametrize("build", BUILDERS)
def test_each_applicable_fact_verifies_alone_and_through_a_plan(full_pack, build):
    pack = build(full_pack)
    by_section: dict[str, list[str]] = {}
    for fact in catalogue(pack):
        if fact.id.startswith("investigation.") and fact.section != SECTION_INVESTIGATION:
            by_section.setdefault(fact.section, []).append(fact.id)
    for section, ids in by_section.items():
        for fact_id in ids:
            narrative = render_plan(pack, RenderPlan(sections={section: [fact_id]}))
            assert SPEC_BY_ID[fact_id].render(pack) in text(narrative)
            assert verify(text(narrative), pack).passed, fact_id


def test_every_spec_has_a_label_a_known_source_and_is_covered_by_some_builder(full_pack):
    from veedor.domain.dossier.source_catalog import INVESTIGATION_SOURCES

    seen = set()
    for build in BUILDERS:
        seen |= {f.id for f in catalogue(build(full_pack))}
    for spec in FACT_SPECS:
        assert spec.label_es.strip() and (spec.source_key is None or spec.source_key in INVESTIGATION_SOURCES)
        assert spec.id in seen, f"no test pack exercises {spec.id}"


def test_no_investigation_means_no_investigation_facts(full_pack, minimal_pack):
    for pack in (full_pack, minimal_pack):
        assert not [f for f in catalogue(pack) if f.id.startswith("investigation.")]


def test_a_failed_lookup_says_no_disponible_and_states_no_value(full_pack):
    body = text(render_template(failed(full_pack)))
    assert body.count("no disponible (la fuente no respondió)") >= 5
    assert "Capital suscrito" not in body and "Situación legal según" not in body
    assert "no se consultó" in body


def test_the_investigation_section_cannot_be_planned_or_hidden(full_pack):
    pack = full(full_pack)
    with pytest.raises(PlanError):
        validate_plan(RenderPlan(sections={SECTION_INVESTIGATION: ["investigation.run.note"]}), pack)
    rendered = text(render_plan(pack, RenderPlan(sections={"Contexto comparativo": ["context.count"]})))
    assert (
        "Investigación realizada" in rendered
        and "falló (el servicio de origen devolvió un error); un reintento" in rendered
    )


def test_the_quoted_report_title_is_hidden_from_the_model_catalogue(full_pack):
    from veedor.agents.investigator.prompting import catalogue_payload

    pack = full(full_pack)
    assert "investigation.audit.reports" in UNTRUSTED_QUOTE_IDS
    shown = {f["id"]: f["texto"] for f in catalogue_payload(pack)["hechos"]}
    assert "Examen Especial" not in shown["investigation.audit.reports"]
    assert "DNA1-0001-2023" in shown["investigation.audit.reports"]


def test_a_number_swapped_between_new_labels_is_rejected(full_pack):
    pack = full(full_pack)
    bad = "Capital suscrito: USD 1.234,50."  # the equity value, under the capital label
    assert not verify(bad, pack).passed


def test_a_plan_cannot_hide_investigation_facts(full_pack):
    pack = full(full_pack)
    narrative = render_plan(pack, RenderPlan(sections={"Proveedor adjudicado": ["winner.identity"]}))
    body = text(narrative)
    assert "Capital suscrito" in body and "Consulta en línea al SRI" in body
    assert verify(body, pack).passed
