from __future__ import annotations

import pytest

from veedor.infrastructure.ocds.flatten import extract_ruc, flatten, method_group


def release(**tender_overrides):
    tender = {
        "id": "SIE-001",
        "procurementMethodDetails": "Subasta Inversa Electrónica",
        "mainProcurementCategory": "goods",
        "status": "complete",
        "numberOfTenderers": 2,
        "value": {"amount": 1000.0},
        "tenderPeriod": {"startDate": "2023-05-01T08:00:00-05:00", "endDate": "2023-05-05T15:00:00-05:00"},
        "tenderers": [
            {"id": "EC-RUC-1790000000001", "name": "Alfa S.A."},
            {"id": "EC-RUC-1790000000001", "name": "Alfa S.A."},
            {"id": "EC-RUC-0102030405001", "name": "Beta"},
        ],
        "enquiries": [{"id": 1}],
        "items": [{"classification": {"id": "123456789", "description": "Papel"}}],
    }
    tender.update(tender_overrides)
    return {
        "ocid": "ocds-x-SIE-001",
        "date": "2023-06-01T10:00:00-05:00",
        "buyer": {"id": "EC-RUC-1760001120001", "name": "Entidad"},
        "parties": [{"id": "EC-RUC-1760001120001", "address": {"region": "Pichincha", "locality": "Quito"}}],
        "tender": tender,
        "awards": [
            {
                "id": 1,
                "date": "2023-05-10T09:00:00-05:00",
                "value": {"amount": 900.0},
                "suppliers": [{"id": "EC-RUC-1790000000001", "name": "Alfa S.A."}],
            }
        ],
        "contracts": [{"dateSigned": "2023-05-20T00:00:00-05:00"}],
    }


def test_extract_ruc():
    assert extract_ruc("EC-RUC-1790000000001") == "1790000000001"
    assert extract_ruc("EC-RUC-12") is None
    assert extract_ruc("OTHER-1") is None
    assert extract_ruc(None) is None
    assert extract_ruc(123) is None


@pytest.mark.parametrize(
    ("method", "has_tender", "expected"),
    [
        ("Subasta Inversa Electrónica", True, "competitive"),
        ("Menor Cuantía", True, "competitive"),
        ("Catálogo electrónico - Compra directa", True, "catalogue"),
        ("Bienes y Servicios únicos", True, "direct"),
        ("Contratacion directa", True, "direct"),
        ("Algo nuevo", True, "other"),
        (None, True, "unknown"),
        ("Menor Cuantía", False, "no_tender_block"),
    ],
)
def test_method_group(method, has_tender, expected):
    assert method_group(method, has_tender) == expected


def test_flatten_process_row():
    process, tenderers, awards = flatten(release())
    assert process["ocid"] == "ocds-x-SIE-001"
    assert process["process_code"] == "SIE-001"
    assert process["method_group"] == "competitive"
    assert process["year"] == 2023
    assert process["buyer_ruc"] == "1760001120001"
    assert (process["buyer_region"], process["buyer_locality"]) == ("Pichincha", "Quito")
    assert (process["budget"], process["budget_source"]) == (1000.0, "tender.value")
    assert process["n_tenderers"] == 2 and process["n_tenderers_listed"] == 2
    assert process["n_enquiries"] == 1 and process["n_awards"] == 1
    assert process["award_total"] == 900.0
    assert process["first_award_date"] == "2023-05-10T09:00:00-05:00"
    assert process["date_signed"] == "2023-05-20T00:00:00-05:00"
    assert process["main_cpc"] == "123456789"
    assert process["has_tender_block"] is True
    assert len(tenderers) == 2  # duplicate tenderer collapsed
    assert {t["supplier_ruc"] for t in tenderers} == {"1790000000001", "0102030405001"}
    assert len(awards) == 1 and awards[0]["amount"] == 900.0 and awards[0]["supplier_ruc"] == "1790000000001"


def test_flatten_multi_supplier_award_has_no_split_amount():
    rel = release()
    rel["awards"][0]["suppliers"].append({"id": "EC-RUC-0990000000001", "name": "Gamma"})
    process, _, awards = flatten(rel)
    assert len(awards) == 2 and all(a["amount"] is None for a in awards)
    assert process["award_total"] == 900.0


def test_flatten_budget_fallbacks():
    lots = release(value=None, lots=[{"value": {"amount": 10.0}}, {"value": {"amount": 5.5}}])
    process, _, _ = flatten(lots)
    assert (process["budget"], process["budget_source"]) == (15.5, "tender.lots")
    planning = release(value=None)
    planning["planning"] = {"budget": {"amount": {"amount": 77.0}}}
    process, _, _ = flatten(planning)
    assert (process["budget"], process["budget_source"]) == (77.0, "planning.budget")
    process, _, _ = flatten(release(value=None))
    assert process["budget"] is None and process["budget_source"] is None


def test_flatten_release_without_tender_or_awards():
    process, tenderers, awards = flatten({"ocid": "ocds-x-1", "date": "2020-01-02T00:00:00-05:00"})
    assert process["method_group"] == "no_tender_block" and process["has_tender_block"] is False
    assert process["year"] == 2020 and process["award_total"] is None and process["first_award_date"] is None
    assert tenderers == [] and awards == []
