"""Spanish evidence wording, signal statements, history, revenue, sources and figure binding."""

import re
from pathlib import Path

import pytest

from veedor.domain.dossier import source_catalog
from veedor.domain.dossier.assessment import assess
from veedor.domain.dossier.evidence_text import EVIDENCE_LABELS, signal_statement, unmapped_keys
from veedor.domain.dossier.grounding import verify
from veedor.domain.dossier.models import HistoryFacts, SignalFact
from veedor.domain.dossier.template import render_template

SIGNAL_SQL = Path(__file__).resolve().parents[3] / "src/veedor/infrastructure/lake/marts_builder_sql.py"

EVIDENCE = {
    "SINGLE_BIDDER": {"method": "Subasta Inversa Electrónica", "year": 2023, "n_tenderers": 1},
    "SHORT_TENDER_WINDOW": {
        "method": "Subasta Inversa Electrónica", "year": 2023, "tender_start": "2023-08-02T10:00:00-05:00",
        "tender_end": "2023-08-03T10:00:00-05:00", "window_days": 1.0, "p05_days": 4.04,
        "n_method_year": 8415,
    },
    "LOW_SAVING": {
        "method": "Subasta Inversa Electrónica", "year": 2023, "budget": 27318.51, "award_total": 24490.0,
        "award_to_budget": 0.8965, "p95_ratio": 0.9456, "threshold": 0.9456, "n_method_year": 362,
    },
    "NEW_SUPPLIER": {
        "supplier_ruc": "1790012345001", "supplier_name": "COMERCIAL ANDES S.A.",
        "activity_start_date": "2023-05-22", "first_award_date": "2023-08-25", "days_between": 95,
    },
    "SUPPLIER_NOT_ACTIVE": {
        "supplier_ruc": "1790012345001", "supplier_name": "COMERCIAL ANDES S.A.", "sri_status": "SUSPENDIDO",
        "status_is_current": True, "suspension_date": "2020-10-03", "restart_date": None,
        "process_date": "2023-08-25", "timing": "suspended_before_process",
    },
    "GHOST_COMPANY_LIST": {
        "supplier_ruc": "1790012345001", "supplier_name": "COMERCIAL ANDES S.A.",
        "resolution": "DZ8-IDIRASC23-00000013-M", "notification_date": "2021-09-27",
        "qualification_detail": "SOCIEDAD CON TRANSACCIONES INEXISTENTES",
        "challenge_state": "FINALIZADO", "first_award_date": "2023-08-25", "listed_after_award": False,
    },
    "BUYER_CONCENTRATION": {
        "year": 2023, "buyer_ruc": "1760001040001", "supplier_ruc": "1790012345001",
        "supplier_name": "COMERCIAL ANDES S.A.", "supplier_amount": 99911.18, "buyer_total": 139388.01,
        "share": 0.7168, "n_awards_buyer_year": 3,
    },
    "REPEATED_DIRECT_AWARDS": {
        "buyer_ruc": "1760001040001", "supplier_ruc": "1790012345001", "cpc_prefix": "53290",
        "n_in_window": 3, "window_days": 90, "window_start": "2023-01-31", "window_end": "2023-04-30",
        "n_same_buyer_supplier_cpc": 6,
    },
    "RECURRING_COBIDDERS": {
        "buyer_ruc": "1760001040001", "winner_ruc": "1790012345001", "winner_name": "COMERCIAL ANDES S.A.",
        "cobidder_ruc": "1790099999001", "cobidder_name": "OTRA EMPRESA S.A.", "n_meetings": 5,
        "n_recurring_cobidders_in_process": 1,
    },
    "CONTRACT_VS_COMPANY_SIZE": {
        "supplier_ruc": "1790012345001", "supplier_name": "COMERCIAL ANDES S.A.", "award_total": 24490.0,
        "revenue": 150.0, "revenue_year": 2023, "ratio": 163.27, "factor": 3.0,
    },
}  # fmt: skip


def _signal(code, value=1.0, threshold=1.0, **evidence):
    return SignalFact(code=code, label_es=f"Etiqueta {code}", value=value, threshold=threshold,
                      evidence=evidence or EVIDENCE[code])  # fmt: skip


@pytest.fixture
def all_signals_pack(full_pack):
    signals = [_signal(code) for code in EVIDENCE]
    return assess(full_pack.model_copy(update={"signals": signals}))


def _text(pack):
    n = render_template(pack)
    return "\n".join([n.summary_es, *[s.body for s in n.sections]])


# 1 ---------------------------------------------------------------------------------------------
def test_every_evidence_key_emitted_by_the_marts_builder_has_a_spanish_label():
    source = SIGNAL_SQL.read_text()
    blocks = re.findall(r"json_object\((.*?)\)::VARCHAR", source, flags=re.S)
    keys = {k for block in blocks for k in re.findall(r"'([a-z][a-z0-9_]*)',", block)}
    assert len(keys) > 30
    assert not [k for k in keys - {"day", "prior_year", "same_year"} if k not in EVIDENCE_LABELS]


def test_every_label_is_spanish_and_visible_kinds_have_text():
    for key, (label, kind) in EVIDENCE_LABELS.items():
        assert (label == "") == (kind == "hidden"), key
        assert "_" not in label and not re.search(r"\b(status|date|year of|tenderers)\b", label), key


def test_no_raw_english_key_or_flag_reaches_the_prose(all_signals_pack):
    text = _text(all_signals_pack)
    for key in EVIDENCE_LABELS:
        if "_" in key:
            assert key not in text, key
    for phrase in ("status is current", "n tenderers", "sri status", "award total", "revenue year"):
        assert phrase not in text
    assert "ingresos reportados" in text and "estado en el SRI" in text and "número de oferentes" in text


def test_unmapped_keys_are_never_printed_and_are_detectable(full_pack):
    odd = _signal("SINGLE_BIDDER", method="Menor", brand_new_key=7, other_new_key="x")
    assert unmapped_keys(odd.evidence) == ["brand_new_key", "other_new_key"]
    text = _text(assess(full_pack.model_copy(update={"signals": [odd]})))
    assert "brand_new_key" not in text and "brand new key" not in text


def test_amounts_use_usd_with_ecuadorian_separators(all_signals_pack):
    text = _text(all_signals_pack)
    assert "monto adjudicado USD 24.490,00" in text and "ingresos reportados USD 150,00" in text


# 2 ---------------------------------------------------------------------------------------------
def test_contract_size_statement_is_readable():
    s = _signal("CONTRACT_VS_COMPANY_SIZE", value=260.9067, threshold=3.0, award_total=39136.0,
                revenue=150.0, revenue_year=2019, ratio=260.91, factor=3.0)  # fmt: skip
    assert signal_statement(s) == (
        "El monto adjudicado (USD 39.136,00) equivale a 260,9 veces los ingresos reportados por la "
        "empresa para 2019 (USD 150,00); el umbral de la señal es 3 veces."
    )


def test_every_signal_has_a_specific_statement_and_value_is_secondary(all_signals_pack):
    for code in EVIDENCE:
        statement = signal_statement(_signal(code))
        assert not statement.startswith("Se activó el indicador"), code
    line = next(s for s in _text(all_signals_pack).splitlines() if s.startswith("- Etiqueta CONTRACT"))
    assert line.index("equivale a") < line.index("Dato técnico")


def test_unknown_signal_gets_a_generic_statement():
    assert signal_statement(SignalFact(code="NEW", label_es="Nuevo indicador")) == (
        "Se activó el indicador «Nuevo indicador»."
    )


def test_signal_value_is_not_printed_with_spurious_precision():
    s = _signal("CONTRACT_VS_COMPANY_SIZE", value=260.9067, threshold=3.0)
    from veedor.domain.dossier.template import _signal_line

    assert "260,91" in _signal_line(s) and "260,9067" not in _signal_line(s)


# 3 ---------------------------------------------------------------------------------------------
def test_source_catalog_uses_the_documented_licences():
    sercop = source_catalog.sercop("Procesos", "ocid-1")
    assert (sercop.licence, sercop.retrieved_at) == ("CC BY 3.0 EC", "2026-11-16")
    assert sercop.url == "https://data.open-contracting.org/en/publication/110"
    for source in (source_catalog.sri("SRI", "1"), source_catalog.supercias("Supercías", "1")):
        assert source.licence == "licencia no declarada por la fuente"
    assert source_catalog.veedor_indicators("o", "2026-11-16").licence.startswith("MIT")


# 4 ---------------------------------------------------------------------------------------------
def _history(**kw):
    base = dict(reference_date="2023-08-25", reference_date_kind="fecha de adjudicación", n_previous_awards=0,
                n_with_amount=0, n_pair_awards=3, pair_first_year=2019, pair_last_year=2021)  # fmt: skip
    return HistoryFacts(**{**base, **kw})


def _relation(pack, history):
    n = render_template(assess(pack.model_copy(update={"history": history})))
    return next(s.body for s in n.sections if s.title.startswith("Relación"))


def test_history_three_outputs(full_pack):
    previous = _history(n_previous_awards=2, n_with_amount=2, total_previous_amount=900.5,
                        first_award_date="2022-01-02", last_award_date="2023-02-03")  # fmt: skip
    prior = _relation(full_pack, previous)
    assert "2 adjudicaciones previas" in prior and "USD 900,50" in prior
    assert "Primera adjudicación previa: 2 de enero de 2022" in prior
    assert "fecha de adjudicación: 25 de agosto de 2023" in prior
    none_prior = _relation(full_pack, _history())
    assert "Sin adjudicaciones previas registradas entre esta entidad y este proveedor" in none_prior
    assert "no disponible" not in none_prior
    missing = _relation(full_pack, None)
    assert "no disponible" in missing


def test_history_states_the_reference_date_used_and_pair_totals(full_pack):
    text = _relation(
        full_pack, _history(reference_date_kind="inicio de ofertas", reference_date="2019-08-08")
    )
    assert "inicio de ofertas: 8 de agosto de 2019" in text
    assert (
        "En total, el conjunto de datos registra 3 adjudicaciones de esta entidad a este proveedor " in text
    )
    assert "entre 2019 y 2021" in text
    single = _relation(full_pack, _history(n_pair_awards=1, pair_first_year=2020, pair_last_year=2020))
    assert "una adjudicación" in single and " en 2020 " in single


def test_history_texts_pass_grounding(full_pack):
    one = _history(n_previous_awards=1, n_with_amount=1, total_previous_amount=5.0,
                   first_award_date="2022-01-02", last_award_date="2022-01-02")  # fmt: skip
    for history in (_history(), one):
        pack = assess(full_pack.model_copy(update={"history": history}))
        assert verify(_text(pack), pack).passed


# 5 ---------------------------------------------------------------------------------------------
def test_revenue_lines_name_the_year_of_each_figure(full_pack):
    text = _text(full_pack)
    assert "Ingresos del año del proceso: USD 98.000,25 (año 2023)." in text
    assert "Ingresos más recientes reportados: USD 150.000,50 (año 2022)." in text


def test_revenue_of_the_award_year_unavailable_is_said(full_pack):
    registry = full_pack.winner.registry.model_copy(update={"revenue_award_year": None})
    pack = full_pack.model_copy(update={"winner": full_pack.winner.model_copy(update={"registry": registry})})
    assert "Ingresos del año del proceso: no disponible (año 2023)." in _text(pack)
    assert verify(_text(pack), pack).passed


def test_same_year_revenue_is_not_repeated(full_pack):
    registry = full_pack.winner.registry.model_copy(
        update={"latest_revenue_year": 2023, "latest_revenue": 98000.25}
    )
    pack = full_pack.model_copy(update={"winner": full_pack.winner.model_copy(update={"registry": registry})})
    assert "Ingresos más recientes" not in _text(pack)


# 6 ---------------------------------------------------------------------------------------------
def test_unknown_timing_says_activity_at_process_time_cannot_be_established():
    s = _signal("SUPPLIER_NOT_ACTIVE", sri_status="PASIVO", suspension_date=None, process_date="2023-08-25",
                timing="unknown")  # fmt: skip
    assert (
        "no es posible establecer si el proveedor estaba activo al momento del proceso" in signal_statement(s)
    )


def test_missing_timing_key_is_treated_as_unknown():
    s = _signal("SUPPLIER_NOT_ACTIVE", sri_status="PASIVO", suspension_date="2024-01-01")
    assert "no es posible establecer" in signal_statement(s)


def test_suspension_before_process_is_stated():
    text = signal_statement(_signal("SUPPLIER_NOT_ACTIVE"))
    assert "suspensión del 3 de octubre de 2020 es anterior" in text and "no es posible" not in text


# 7 ---------------------------------------------------------------------------------------------
def test_swapped_budget_and_award_are_rejected(full_pack):
    ok = "El presupuesto referencial fue de USD 27.318,51 y el monto adjudicado fue de USD 24.490,00."
    swapped = "El presupuesto referencial fue de USD 24.490,00 y el monto adjudicado fue de USD 27.318,51."
    assert verify(ok, full_pack).passed
    report = verify(swapped, full_pack)
    assert not report.passed and len(report.unsupported) == 2
    assert all("does not belong" in t.reason for t in report.unsupported)


def test_swapped_percentages_dates_and_counts_are_rejected(full_pack):
    assert verify("La proporción de procesos con un solo oferente fue 12,3 %.", full_pack).passed
    assert not verify("La proporción de procesos con un solo oferente fue 94,6 %.", full_pack).passed
    assert verify("La fecha de adjudicación fue el 25 de agosto de 2023.", full_pack).passed
    assert not verify("La fecha de adjudicación fue el 1 de septiembre de 2023.", full_pack).passed
    assert not verify("La fecha de firma fue el 25 de agosto de 2023.", full_pack).passed
    assert not verify("La mediana de oferentes fue 1.", full_pack).passed


def test_binding_applies_only_to_a_figure_that_directly_follows_the_label(full_pack):
    text = "El monto adjudicado equivale a una fracción del presupuesto, y el total fue USD 27.318,51."
    assert verify(text, full_pack).passed  # not directly after a label: membership only
    assert verify("Presupuesto referencial: USD 27.318,51. Monto adjudicado: USD 24.490,00 (89,7 %).",
                  full_pack).passed  # fmt: skip


def test_binding_covers_evidence_values_of_the_pack(all_signals_pack):
    assert verify("El monto adjudicado fue de USD 24.490,00.", all_signals_pack).passed
    assert not verify("Los ingresos reportados fueron de USD 24.490,00.", all_signals_pack).passed
    assert verify("Los ingresos reportados fueron de USD 150,00.", all_signals_pack).passed


def test_label_without_a_pack_value_rejects_any_figure(minimal_pack):
    assert not verify("El presupuesto referencial fue de USD 100,00.", minimal_pack).passed


# 8 ---------------------------------------------------------------------------------------------
def test_all_signals_template_passes_grounding(all_signals_pack):
    report = verify(_text(all_signals_pack), all_signals_pack)
    assert report.passed, [t.model_dump() for t in report.unsupported + report.forbidden]
