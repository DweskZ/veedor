from __future__ import annotations

import sys
import types
from typing import ClassVar

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient

API = "/api/v1"


def test_health_lists_tables(client: TestClient) -> None:
    body = client.get(f"{API}/health").json()
    assert body["status"] == "ok" and body["tables"]["process_scores"] is True
    assert body["tables"]["ghost_companies"] is False


def test_stats(client: TestClient) -> None:
    body = client.get(f"{API}/stats").json()
    assert body["processes_scored"] == 5 and body["processes_total"] == 5
    assert body["signal_counts"][0]["label_es"] in {"Oferente único", "Ahorro atípicamente bajo"}


def test_processes_list_default_sort_and_envelope(client: TestClient) -> None:
    body = client.get(f"{API}/processes").json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["page_size"] == 25 and body["items"][0]["ocid"] == fx.OCID_COMPANY


def test_processes_filters_and_paging(client: TestClient) -> None:
    body = client.get(
        f"{API}/processes", params={"signal": "SINGLE_BIDDER", "page_size": 1, "page": 2}
    ).json()
    assert body["total"] == 3 and len(body["items"]) == 1


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page_size": 101},
        {"page_size": 0},
        {"year": 1800},
        {"min_score": 101},
        {"signal": "NOT_A_SIGNAL"},
        {"sort": "bogus"},
        {"sort": "risk_score; DROP TABLE reviews"},
    ],
)
def test_invalid_query_params_are_422(client: TestClient, params: dict) -> None:
    response = client.get(f"{API}/processes", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] in {"validation_error", "invalid_sort"}


def test_process_detail(client: TestClient) -> None:
    body = client.get(f"{API}/processes/{fx.OCID_COMPANY}").json()
    assert [s["code"] for s in body["signals"]] == [
        "GHOST_COMPANY_LISTED_LATER",
        "LOW_SAVING",
        "SINGLE_BIDDER",
    ]
    assert body["winner"]["name"] == fx.COMPANY_NAME
    assert body["facts"]["buyer_name"] == fx.BUYER_NAME
    assert "No constituyen una acusación" in body["notice_es"]


def test_process_detail_tolerates_bad_evidence_json(client: TestClient) -> None:
    body = client.get(f"{API}/processes/ocds-5wno2w-test-0005").json()
    assert body["signals"][0]["evidence"] == {}


def test_unknown_process_is_404_with_error_model(client: TestClient) -> None:
    response = client.get(f"{API}/processes/ocds-5wno2w-nothing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_supplier_and_buyer(client: TestClient) -> None:
    supplier = client.get(f"{API}/suppliers/{fx.COMPANY_RUC}").json()
    assert (
        supplier["profile"]["name"] == fx.COMPANY_NAME and supplier["registry"]["sri"]["status"] == "ACTIVO"
    )
    buyer = client.get(f"{API}/buyers/{fx.BUYER_RUC}").json()
    assert buyer["n_processes"] == 3 and buyer["top_suppliers"][0]["ruc"] == fx.COMPANY_RUC


def test_signal_catalogue(client: TestClient) -> None:
    body = client.get(f"{API}/signals").json()
    assert {s["code"] for s in body} >= {"SINGLE_BIDDER", "LOW_SAVING"}
    assert all(s["label_es"] and s["threshold_rule_es"] for s in body)


def test_missing_marts_return_503_json(empty_client: TestClient) -> None:
    for path in ("/stats", "/processes", f"/processes/{fx.OCID_COMPANY}", f"/suppliers/{fx.COMPANY_RUC}"):
        response = empty_client.get(API + path)
        assert response.status_code == 503, path
        assert response.json()["error"]["code"] == "data_unavailable"
        assert "Traceback" not in response.text
    assert empty_client.get(f"{API}/health").status_code == 200


def test_dossier_503_when_builder_missing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "veedor.use_cases.build_dossier", None)
    response = client.get(f"{API}/processes/{fx.OCID_COMPANY}/dossier")
    assert response.status_code == 503 and response.json()["error"]["code"] == "dossier_unavailable"


class _FakeService:
    calls: ClassVar[list[bool]] = []

    def __init__(self, use_llm: bool) -> None:
        self.calls.append(use_llm)

    def build(self, ocid: str) -> dict:
        return {
            "ocid": ocid,
            "mode": "template",
            "summary_es": f"Adjudicado a {fx.NATURAL_NAME} ({fx.NATURAL_RUC}).",
            "sections": [{"title": "Ganador", "winner": {"ruc": fx.NATURAL_RUC, "name": fx.NATURAL_NAME}}],
            "extra_field": {"supplier_ruc": fx.NATURAL_RUC, "supplier_name": fx.NATURAL_NAME},
        }


def test_dossier_delegates_and_masks(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("veedor.use_cases.build_dossier")
    fake.default_service = lambda use_llm=True, write_traces=True: _FakeService(use_llm)
    monkeypatch.setitem(sys.modules, "veedor.use_cases.build_dossier", fake)
    response = client.get(f"{API}/processes/{fx.OCID_NATURAL}/dossier")
    assert response.status_code == 200
    assert fx.NATURAL_NAME not in response.text and fx.NATURAL_RUC not in response.text
    assert response.json()["sections"][0]["winner"]["name"] == "Persona natural"
    assert _FakeService.calls[-1] is False  # the API never asks for an LLM-backed service


def test_dossier_404_for_unknown_process(client: TestClient) -> None:
    assert client.get(f"{API}/processes/ocds-5wno2w-nothing/dossier").status_code == 404


def test_openapi_documents_the_contract(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    assert {
        f"{API}/health", f"{API}/stats", f"{API}/processes", f"{API}/processes/{{ocid}}",
        f"{API}/processes/{{ocid}}/dossier", f"{API}/suppliers/{{ruc}}", f"{API}/buyers/{{ruc}}",
        f"{API}/signals", f"{API}/processes/{{ocid}}/reviews",
    } <= paths  # fmt: skip
