"""Free-text masking, parties without a RUC, withheld descriptions and the supplier oracle."""

from __future__ import annotations

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient

API = "/api/v1"
UNIDENTIFIED = "Persona natural o sin identificar"


def test_description_with_natural_person_winner_is_withheld(client: TestClient) -> None:
    facts = client.get(f"{API}/processes/{fx.OCID_NATURAL}").json()["facts"]
    assert facts["description"] is None and facts["description_withheld"] is True


def test_description_withheld_when_masking_finds_an_honorific_name(client: TestClient) -> None:
    response = client.get(f"{API}/processes/{fx.OCID_DIRECT}")
    facts = response.json()["facts"]
    assert facts["description"] is None and facts["description_withheld"] is True
    assert fx.DOCTOR_NAME not in response.text


def test_clean_description_is_kept(client: TestClient) -> None:
    facts = client.get(f"{API}/processes/{fx.OCID_COMPANY}").json()["facts"]
    assert facts["description"] == "Construcción de aceras y bordillos"
    assert facts["description_withheld"] is False


def test_party_without_ruc_is_masked_everywhere(client: TestClient) -> None:
    response = client.get(f"{API}/processes/{fx.OCID_NORUC}")
    body = response.json()
    for token in ("MENDEZ", "ROJAS", "JOSE ANTONIO", fx.CEDULA):
        assert token not in response.text
    assert body["winner"] == {"ruc": None, "name": UNIDENTIFIED, "kind": "unknown"} | {
        k: v for k, v in body["winner"].items() if k not in {"ruc", "name", "kind"}
    }
    names = {t["name"] for t in body["tenderers"]}
    assert names == {UNIDENTIFIED, fx.ENTITY_NORUC_NAME}  # the legal entity is allow-listed
    assert body["awards"][0]["supplier_name"] == UNIDENTIFIED
    assert body["facts"]["description"] is None and body["facts"]["description_withheld"] is True


def test_list_masks_winner_without_ruc(client: TestClient) -> None:
    rows = {r["ocid"]: r for r in client.get(f"{API}/processes").json()["items"]}
    row = rows[fx.OCID_NORUC]
    assert (row["winner_name"], row["winner_ruc"], row["winner_kind"]) == (UNIDENTIFIED, None, "unknown")
    assert rows["ocds-5wno2w-test-0005"]["winner_name"] is None  # no name, nothing to mask


@pytest.mark.parametrize("text", [fx.NATURAL_NAME, "MENDEZ", fx.CEDULA, fx.DOCTOR_NAME])
def test_q_cannot_find_a_process_through_personal_text(client: TestClient, text: str) -> None:
    assert client.get(f"{API}/processes", params={"q": text}).json()["total"] == 0


def test_q_still_matches_ocid_code_buyer_and_cpc(client: TestClient) -> None:
    for text in ("test-0001", "LICS-006", "Hospital", "Obras de aceras"):
        assert client.get(f"{API}/processes", params={"q": text}).json()["total"] >= 1, text


def test_dossier_text_is_masked_for_names_cedulas_and_honorifics(client: TestClient, monkeypatch) -> None:
    import sys
    import types

    class Service:
        def build(self, ocid: str) -> dict:
            return {
                "ocid": ocid,
                "summary_es": f"Contrato con Ing. Pedro Salazar, CC {fx.CEDULA}, y {fx.NORUC_NAME}.",
                "sections": [],
            }

    fake = types.ModuleType("veedor.use_cases.build_dossier")
    fake.default_service = lambda use_llm=True, write_traces=True: Service()
    monkeypatch.setitem(sys.modules, "veedor.use_cases.build_dossier", fake)
    text = client.get(f"{API}/processes/{fx.OCID_NORUC}/dossier").text
    for leaked in ("Salazar", fx.CEDULA, "MENDEZ"):
        assert leaked not in text


def test_dossier_builder_failure_is_a_controlled_503(client: TestClient, monkeypatch) -> None:
    import sys
    import types

    class Boom:
        def build(self, ocid: str) -> dict:
            raise RuntimeError("GroundingError: secret internals")

    fake = types.ModuleType("veedor.use_cases.build_dossier")
    fake.default_service = lambda use_llm=True, write_traces=True: Boom()
    monkeypatch.setitem(sys.modules, "veedor.use_cases.build_dossier", fake)
    response = client.get(f"{API}/processes/{fx.OCID_COMPANY}/dossier")
    assert response.status_code == 503 and response.json()["error"]["code"] == "dossier_unavailable"
    assert "secret" not in response.text


def test_dossier_cache_is_bounded(client: TestClient, monkeypatch, tmp_path) -> None:
    import sys
    import types

    from veedor.core.settings import get_settings
    from veedor.use_cases.queries import dossier as dossier_module

    settings = get_settings()
    monkeypatch.setattr(type(settings), "data_dir", tmp_path, raising=False)
    monkeypatch.setattr(settings, "data_dir", tmp_path, raising=False)
    cache = tmp_path / "dossiers"
    cache.mkdir()
    (cache / "other.json").write_text("{}")
    monkeypatch.setattr(dossier_module, "MAX_API_CACHED_DOSSIERS", 1)

    class Service:
        def build(self, ocid: str) -> dict:
            (cache / f"{ocid}.json").write_text("{}")  # what the real service does
            return {"ocid": ocid}

    fake = types.ModuleType("veedor.use_cases.build_dossier")
    fake.default_service = lambda use_llm=True, write_traces=True: Service()
    monkeypatch.setitem(sys.modules, "veedor.use_cases.build_dossier", fake)
    assert client.get(f"{API}/processes/{fx.OCID_COMPANY}/dossier").status_code == 200
    assert not (cache / f"{fx.OCID_COMPANY}.json").exists()  # cache full: result served, not kept
