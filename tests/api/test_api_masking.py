"""No endpoint may expose a natural person's name or full RUC."""

from __future__ import annotations

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient

API = "/api/v1"
MASKED_RUC = fx.NATURAL_RUC[:4] + "*********"

PATHS = [
    "/processes?page_size=100",
    f"/processes/{fx.OCID_NATURAL}",
    f"/processes/{fx.OCID_NORUC}",
    f"/processes/{fx.OCID_DIRECT}",
    f"/buyers/{fx.BUYER_RUC}",
]


@pytest.mark.parametrize("path", PATHS)
def test_responses_never_contain_natural_person_identity(client: TestClient, path: str) -> None:
    response = client.get(API + path)
    assert response.status_code == 200
    assert fx.NATURAL_NAME not in response.text
    assert "Quispe" not in response.text
    assert fx.NATURAL_RUC not in response.text


def test_list_winner_is_masked_and_company_is_not(client: TestClient) -> None:
    rows = {r["ocid"]: r for r in client.get(f"{API}/processes").json()["items"]}
    natural = rows[fx.OCID_NATURAL]
    assert (natural["winner_name"], natural["winner_ruc"], natural["winner_kind"]) == (
        "Persona natural",
        MASKED_RUC,
        "natural_person",
    )
    company = rows[fx.OCID_COMPANY]
    assert (company["winner_name"], company["winner_ruc"], company["winner_kind"]) == (
        fx.COMPANY_NAME,
        fx.COMPANY_RUC,
        "company",
    )
    assert company["buyer_ruc"] == fx.BUYER_RUC


def test_detail_masks_winner_tenderers_awards_and_evidence(client: TestClient) -> None:
    body = client.get(f"{API}/processes/{fx.OCID_NATURAL}").json()
    assert body["winner"]["name"] == "Persona natural" and body["winner"]["ruc"] == MASKED_RUC
    tenderers = {t["kind"]: t for t in body["tenderers"]}
    assert tenderers["natural_person"] == {
        "ruc": MASKED_RUC,
        "name": "Persona natural",
        "kind": "natural_person",
    }
    assert tenderers["company"]["name"] == fx.COMPANY_NAME
    assert body["awards"][0]["supplier_name"] == "Persona natural"
    evidence = body["signals"][0]["evidence"]
    assert evidence["winner_name"] == "Persona natural" and evidence["winner_ruc"] == MASKED_RUC
    assert evidence["note"] == f"Adjudicado a [persona natural] ({MASKED_RUC})"


def test_supplier_endpoint_is_not_an_oracle_for_natural_persons(client: TestClient) -> None:
    natural = client.get(f"{API}/suppliers/{fx.NATURAL_RUC}")
    unknown = client.get(f"{API}/suppliers/1712399999001")  # natural-person RUC absent from the data
    assert natural.status_code == unknown.status_code == 404
    assert natural.json() == unknown.json()
    assert "Persona" not in natural.text and fx.NATURAL_NAME not in natural.text


def test_company_supplier_is_unchanged(client: TestClient) -> None:
    body = client.get(f"{API}/suppliers/{fx.COMPANY_RUC}").json()
    assert body["profile"]["name"] == fx.COMPANY_NAME and body["registry"]["sri"]["status"] == "ACTIVO"
    assert all(r["winner_name"] == fx.COMPANY_NAME for r in body["recent_processes"])


def test_buyer_top_suppliers_are_masked(client: TestClient) -> None:
    body = client.get(f"{API}/buyers/{fx.BUYER_RUC}").json()
    by_kind = {s["kind"]: s for s in body["top_suppliers"]}
    assert by_kind["natural_person"]["name"] == "Persona natural"
    assert by_kind["natural_person"]["ruc"] == MASKED_RUC
    assert by_kind["company"]["name"] == fx.COMPANY_NAME
