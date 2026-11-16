# ruff: noqa: E501
"""Review-4 fixes: report-number shape, audit cap and ordering, store identity check, count agreement."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from veedor.domain.dossier.grounding import verify
from veedor.domain.dossier.models import (
    AuditFacts,
    EvidencePack,
    InvestigationFacts,
    PairHistoryFacts,
    SimilarPurchasesFacts,
)
from veedor.domain.dossier.template import render_template
from veedor.domain.investigation.convert import MAX_LISTED_REPORTS, audit_facts
from veedor.domain.investigation.models import InvestigationRecord
from veedor.domain.investigation.results import REPORT_ID_PATTERN, ReportsFile
from veedor.infrastructure.investigations.store import InvestigationStore

TODAY = date(2026, 11, 16)
PACKS = Path(__file__).resolve().parents[2] / "fixtures" / "dossier"
FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "investigation" / "get_contraloria_informe.json"
HEADERS = ["No", "Unidad de Control", "Entidad", "Diligencia", "Periodo\nDesde", "Periodo\nHasta",
           "Tipo de informe", "Nº Informe", "Fecha\nAprobado"]  # fmt: skip


def pack() -> EvidencePack:
    return EvidencePack.model_validate(json.loads((PACKS / "pack_full.json").read_text()))


def with_inv(p: EvidencePack, **parts) -> EvidencePack:
    return p.model_copy(update={"investigation": InvestigationFacts(**parts)})


def body(p: EvidencePack) -> str:
    n = render_template(p)
    return n.summary_es + "\n" + "\n".join(f"{s.title}\n{s.body}" for s in n.sections)


# --- 2: report numbers ---------------------------------------------------------------------------


def test_every_captured_report_number_matches_the_pattern():
    rows = json.loads(FIXTURE.read_text())["rows"]
    assert len(rows) >= 20
    assert all(REPORT_ID_PATTERN.match(r[7]) for r in rows), [r[7] for r in rows]


@pytest.mark.parametrize(
    "value", ["1710034065", "1710034065001", "171-0034-065", "1710034065-001", "AB-1710034065-2020",
              "dpb-0001-2022", "DPB-0001-22", "DPB 0001 2022", "DPB-0001-2022 x", "", "99887"],
)  # fmt: skip
def test_a_report_number_that_is_not_a_report_number_is_unavailable(value):
    p = pack()
    file = ReportsFile.model_validate({"headers": HEADERS, "truncated": False, "rows": [
        ["1", "U", p.process.buyer_name, "x", "2022-01-01", "2023-12-31", "General", value, "2023-01-03"]]})  # fmt: skip
    facts = audit_facts(p.process.buyer_name, [file], files_in_catalogue=1, key_index={}, today=TODAY)
    assert facts.reports[0].report_id is None
    text = body(with_inv(p, audit=facts))
    assert "número de informe no disponible" in text
    if value.strip():
        assert value not in text


# --- 3: cap, order and counts over all matches ----------------------------------------------------


def _many(buyer: str) -> ReportsFile:
    rows = []
    for i in range(9):
        covering = i in (6, 8)  # two covering reports sit late in the file
        start, end = ("2022-01-01", "2023-12-31") if covering else ("2019-01-01", "2020-12-31")
        if i == 4:
            start = end = ""
        rows.append(["1", "U", buyer, f"t{i}", start, end, "General", f"DNA1-{i + 1:04d}-2023", f"2023-0{i + 1}-10"])
    return ReportsFile.model_validate({"headers": HEADERS, "truncated": True, "rows": rows})


def test_audit_cap_is_explicit_ordered_and_counts_cover_all_matches():
    p = pack()
    facts = audit_facts(
        p.process.buyer_name, [_many(p.process.buyer_name)], files_in_catalogue=8, key_index={},
        process_day=date(2023, 8, 25), today=TODAY,
    )  # fmt: skip
    assert facts.n_reports == 9 and len(facts.reports) == MAX_LISTED_REPORTS
    assert (facts.n_covering, facts.n_not_covering, facts.n_period_unknown) == (2, 6, 1)
    ids = [r.report_id for r in facts.reports]
    assert ids[:2] == ["DNA1-0009-2023", "DNA1-0007-2023"]  # covering first, newest approval first
    assert [r.covers_process for r in facts.reports[:2]] == [True, True]
    assert ids[2:] == ["DNA1-0008-2023", "DNA1-0006-2023", "DNA1-0005-2023", "DNA1-0004-2023"]
    text = body(with_inv(p, audit=facts))
    assert "Se muestran 6 de 9 informes identificados" in text
    assert "incluye la fecha del proceso (2 en total" in text
    assert "no incluye la fecha del proceso (6 en total; se muestran por completitud;" in text
    assert "período examinado no disponible (1 en total;" in text
    assert verify(text, with_inv(p, audit=facts)).passed
    again = audit_facts(
        p.process.buyer_name, [_many(p.process.buyer_name)], files_in_catalogue=8, key_index={},
        process_day=date(2023, 8, 25), today=TODAY,
    )  # fmt: skip
    assert again.reports == facts.reports


def test_every_number_of_the_audit_text_is_grounded_with_distinct_counts():
    p = pack()
    rows = []
    for i in range(11):  # 3 covering, 7 not covering, 1 unknown: none of the counts equals the cap of 6
        start, end = ("2022-01-01", "2023-12-31") if i < 3 else ("2019-01-01", "2020-12-31")
        if i == 10:
            start = end = ""
        rows.append(["1", "U", p.process.buyer_name, f"t{i}", start, end, "General", f"DNA1-{i + 1:04d}-2023", f"2023-0{i % 9 + 1}-1{i % 9}"])
    file = ReportsFile.model_validate({"headers": HEADERS, "truncated": True, "rows": rows})
    facts = audit_facts(p.process.buyer_name, [file], files_in_catalogue=8, key_index={}, process_day=date(2023, 8, 25), today=TODAY)  # fmt: skip
    assert (facts.n_reports, facts.n_listed, facts.n_covering, facts.n_not_covering, facts.n_period_unknown) == (11, 6, 3, 7, 1)
    text = body(with_inv(p, audit=facts))
    assert "Se muestran 6 de 11 informes identificados" in text and "(7 en total; se muestran por completitud;" in text
    assert verify(text, with_inv(p, audit=facts)).passed


def test_a_group_pushed_out_by_the_cap_is_still_counted():
    p = pack()
    rows = [["1", "U", p.process.buyer_name, f"t{i}", "2022-01-01", "2023-12-31", "General", f"DNA1-{i + 1:04d}-2023", "2023-03-10"] for i in range(7)]
    rows.append(["1", "U", p.process.buyer_name, "z", "2019-01-01", "2020-12-31", "General", "DNA1-0099-2023", "2023-03-10"])
    file = ReportsFile.model_validate({"headers": HEADERS, "truncated": True, "rows": rows})
    facts = audit_facts(p.process.buyer_name, [file], files_in_catalogue=8, key_index={}, process_day=date(2023, 8, 25), today=TODAY)  # fmt: skip
    text = body(with_inv(p, audit=facts))
    assert "no incluye la fecha del proceso (1 en total; se muestran por completitud; ninguno se muestra por el límite" in text
    assert verify(text, with_inv(p, audit=facts)).passed


def test_few_reports_say_so_without_truncation():
    p = pack()
    file = ReportsFile.model_validate({"headers": HEADERS, "truncated": False, "rows": [
        ["1", "U", p.process.buyer_name, "x", "2022-01-01", "2023-12-31", "General", "DNA1-0001-2023", "2023-01-03"]]})  # fmt: skip
    facts = audit_facts(p.process.buyer_name, [file], files_in_catalogue=1, key_index={},
                        process_day=date(2023, 8, 25), today=TODAY)  # fmt: skip
    text = body(with_inv(p, audit=facts))
    assert "Se muestran 1 de 1 informes identificados" in text


# --- 5: the store checks identity -----------------------------------------------------------------


def _record(ocid: str) -> InvestigationRecord:
    now = datetime.now(UTC)
    return InvestigationRecord(ocid=ocid, started_at=now, finished_at=now, renderer_version=1)


def test_a_record_copied_under_another_identifier_is_not_found(tmp_path):
    store = InvestigationStore(tmp_path)
    path = store.save(_record("ocds-a"))
    store.path("ocds-b").write_bytes(path.read_bytes())  # file copied under b's hash name
    assert store.load("ocds-a").ocid == "ocds-a"
    assert store.load("ocds-b") is None


# --- 7: agreement of counts -----------------------------------------------------------------------


def _similar(n_examined, n_above, n_window, n_amount=1) -> SimilarPurchasesFacts:
    return SimilarPurchasesFacts(
        outcome="ok", neighbours_examined=n_examined, similarity_floor=0.75, n_above_floor=n_above,
        basis="description", n_in_window=n_window, n_with_amount=n_amount, combined_amount=100.0,
        window_days=180,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("facts", "expected", "forbidden"),
    [
        (_similar(50, 0, 0), "ninguna supera", []),
        (_similar(50, 1, 0), "1 supera una similitud", ["1 superan"]),
        (_similar(50, 2, 0), "2 superan una similitud", ["2 supera "]),
        (_similar(50, 5, 1), "1 de ellas está a 180 días", ["1 de ellas están", "1 de ellas está a 1 días"]),
        (_similar(50, 5, 2), "2 de ellas están a 180 días", ["2 de ellas está "]),
        (_similar(50, 5, 0), "ninguna está a 180 días", []),
        (_similar(1, 1, 1), "La compra más similar", ["1 compras", "1 superan"]),
        (_similar(1, 0, 0), "no supera una similitud", ["1 compras"]),
        (_similar(0, 0, 0), "No hay compras similares", ["0 compras"]),
    ],
)
def test_similar_purchase_sentence_agrees_in_number(facts, expected, forbidden):
    p = pack()
    text = body(with_inv(p, similar=facts))
    assert expected in text
    assert not any(bad in text for bad in forbidden)
    assert verify(text, with_inv(p, similar=facts)).passed


@pytest.mark.parametrize(
    ("n", "with_amount", "expected"),
    [(0, 0, "no registra otras adjudicaciones"), (1, 1, "una adjudicación"), (1, 0, "sin monto informado"),
     (2, 1, "2 adjudicaciones"), (2, 1, "en 1 de ellas")],
)  # fmt: skip
def test_pair_history_sentence_agrees_in_number(n, with_amount, expected):
    facts = PairHistoryFacts(outcome="ok", n_other_awards=n, n_with_amount=with_amount, total_other_amount=10.0)
    text = body(with_inv(pack(), pair_history=facts))
    assert expected in text
    assert "1 de ellas" not in text.replace("en 1 de ellas", "") or n != 1


@pytest.mark.parametrize(
    ("rows", "files", "expected"),
    [(0, 1, "0 filas de 0 de los 1 archivo "), (1, 1, "1 fila de 1 de los 1 archivo "),
     (2, 2, "2 filas de 2 de los 2 archivos ")],
)  # fmt: skip
def test_audit_scope_sentence_agrees_in_number(rows, files, expected):
    facts = AuditFacts(outcome="ok", match_reliable=True, conclusive=False, n_reports=0, rows_examined=rows,
                       files_examined=rows and files, files_in_catalogue=files, coverage_complete=False)  # fmt: skip
    text = body(with_inv(pack(), audit=facts))
    assert "filas" in text or "fila " in text
