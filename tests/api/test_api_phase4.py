"""Second review: name consistency, transient lake errors, review hardening, natural buyers/winners."""

from __future__ import annotations

import sys
import types

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient

API = "/api/v1"
DIRECT = f"{API}/processes/{fx.OCID_DIRECT}"


def _fake_builder(monkeypatch: pytest.MonkeyPatch, content: dict, seen: list | None = None) -> None:
    class Service:
        def build(self, ocid: str) -> dict:
            return {"ocid": ocid, **content}

    def default_service(use_llm: bool = True, write_traces: bool = True) -> Service:
        if seen is not None:
            seen.append({"use_llm": use_llm, "write_traces": write_traces})
        return Service()

    fake = types.ModuleType("veedor.use_cases.build_dossier")
    fake.default_service = default_service
    monkeypatch.setitem(sys.modules, "veedor.use_cases.build_dossier", fake)


# --- 1. entity names are not garbled by the honorific rule


def test_dossier_and_detail_show_the_same_buyer_name(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_builder(
        monkeypatch,
        {
            "summary_es": f"La entidad contratante es {fx.HOSPITAL_NAME}.",
            "sections": [{"title": "Entidad", "body": f"«{fx.HOSPITAL_NAME}» contrató con la empresa."}],
            "facts": {"buyer_name": fx.HOSPITAL_NAME, "buyer_ruc": fx.OTHER_BUYER_RUC},
        },
    )
    detail = client.get(DIRECT).json()
    dossier = client.get(f"{DIRECT}/dossier")
    assert detail["facts"]["buyer_name"] == fx.HOSPITAL_NAME
    assert dossier.json()["facts"]["buyer_name"] == fx.HOSPITAL_NAME
    assert fx.HOSPITAL_NAME in dossier.json()["summary_es"]
    assert f"«{fx.HOSPITAL_NAME}»" in dossier.json()["sections"][0]["body"]
    assert "[persona natural]" not in dossier.text


def test_honorific_outside_an_entity_name_is_still_masked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_builder(monkeypatch, {"summary_es": f"Asesoría del Dr. Pedro Salazar a {fx.HOSPITAL_NAME}."})
    summary = client.get(f"{DIRECT}/dossier").json()["summary_es"]
    assert "Salazar" not in summary and fx.HOSPITAL_NAME in summary


# --- 2. transient lake errors


def test_lake_io_error_retries_then_succeeds(lake_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    import duckdb

    from veedor.infrastructure.lake import reader as reader_module
    from veedor.infrastructure.lake.reader import LakeReader

    monkeypatch.setattr(reader_module, "RETRY_BACKOFF_SECONDS", 0)
    lake = LakeReader(*lake_dirs)
    real = lake._run
    calls = []

    def flaky(*args):
        calls.append(1)
        if len(calls) == 1:
            raise duckdb.IOException("Cannot open file x.parquet: Permission denied")
        return real(*args)

    monkeypatch.setattr(lake, "_run", flaky)
    assert lake.fetch("SELECT count(*) AS n FROM process_scores", tables=("process_scores",))[0]["n"] == 5
    assert len(calls) == 2


def test_lake_io_error_that_persists_is_503(lake_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    import duckdb

    from veedor.api.deps import get_reader
    from veedor.api.main import create_app
    from veedor.infrastructure.lake import reader as reader_module
    from veedor.infrastructure.lake.reader import LakeReader

    monkeypatch.setattr(reader_module, "RETRY_BACKOFF_SECONDS", 0)
    lake = LakeReader(*lake_dirs)

    def always(*args):
        raise duckdb.IOException("Cannot open file x.parquet: Permission denied")

    monkeypatch.setattr(lake, "_run", always)
    app = create_app()
    app.dependency_overrides[get_reader] = lambda: lake
    with TestClient(app) as bad:
        response = bad.get(f"{API}/processes")
    assert response.status_code == 503 and response.json()["error"]["code"] == "data_unavailable"
    assert "Permission" not in response.text


# --- 3. review hardening


@pytest.mark.parametrize(
    "note",
    [
        "robaron el contrato",
        "fr4ude",
        "c0rrupto",
        "frаude",  # Cyrillic a
        "ｆｒａｕｄｅ",  # fullwidth
        "fráude",  # combining accent
        "co​rrupto",  # zero-width space
        "H3CH0 il3gal",
    ],
)
def test_wording_variants_are_rejected(db_client: TestClient, note: str) -> None:
    url = f"{API}/processes/{fx.OCID_COMPANY}/reviews"
    response = db_client.post(url, json={"status": "pending", "note": note}, headers=fx.REVIEW_HEADERS)
    assert response.status_code == 422, note
    assert response.json()["error"]["code"] == "forbidden_wording"


def test_review_note_masks_the_process_party_names(db_client: TestClient) -> None:
    url = f"{API}/processes/{fx.OCID_NORUC}/reviews"
    body = db_client.post(
        url,
        json={"status": "pending", "note": f"Revisar a {fx.NORUC_NAME} con detalle"},
        headers=fx.REVIEW_HEADERS,
    ).json()
    assert "MENDEZ" not in body["note"] and "[persona natural]" in body["note"]


_T = fx.REVIEW_TOKEN
BAD_HEADERS = [f"Basic {_T}", f"Bearer  {_T}", f"Bearer\t{_T}", f"Token {_T}", _T, f"Bearer {_T} extra"]


@pytest.mark.parametrize("header", BAD_HEADERS)
def test_only_a_plain_bearer_header_is_accepted(client: TestClient, header: str) -> None:
    url = f"{API}/processes/{fx.OCID_COMPANY}/reviews"
    assert client.post(url, json={"status": "bogus"}, headers={"Authorization": header}).status_code == 401


def test_bearer_scheme_is_case_insensitive(client: TestClient) -> None:
    url = f"{API}/processes/{fx.OCID_COMPANY}/reviews"
    response = client.post(
        url, json={"status": "bogus"}, headers={"Authorization": f"bEaReR {fx.REVIEW_TOKEN}"}
    )
    assert response.status_code == 422  # authenticated, then rejected for the invalid body


def test_anonymous_requests_cannot_exhaust_the_review_rate_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from veedor.api import security

    monkeypatch.setattr(security.review_rate_limiter, "limit", 2)
    url = f"{API}/processes/{fx.OCID_COMPANY}/reviews"
    for _ in range(10):
        assert client.post(url, json={"status": "pending"}).status_code == 401
    ok = client.post(url, json={"status": "bogus"}, headers=fx.REVIEW_HEADERS)
    assert ok.status_code == 422  # not 429


# --- 4. natural-person buyers


def test_natural_person_buyer_is_a_404_like_an_unknown_buyer(client: TestClient) -> None:
    natural = client.get(f"{API}/buyers/{fx.NATURAL_BUYER_RUC}")
    unknown = client.get(f"{API}/buyers/1712999999001")
    assert natural.status_code == unknown.status_code == 404 and natural.json() == unknown.json()


def test_natural_buyer_name_is_not_searchable_or_sortable(client: TestClient) -> None:
    assert client.get(f"{API}/processes", params={"q": "Compradora"}).json()["total"] == 0
    assert client.get(f"{API}/processes", params={"buyer_ruc": fx.NATURAL_BUYER_RUC}).json()["total"] == 0
    rows = client.get(f"{API}/processes", params={"sort": "buyer_name", "page_size": 100})
    assert fx.NATURAL_BUYER_NAME not in rows.text
    ordered = [r["ocid"] for r in rows.json()["items"]]
    assert ordered[-1] == "ocds-5wno2w-test-0005"  # masked buyer sorts as unknown, last


# --- 5. natural-person winners expose no behavioural profile


def test_natural_winner_block_has_only_the_label(client: TestClient) -> None:
    winner = client.get(f"{API}/processes/{fx.OCID_NATURAL}").json()["winner"]
    assert winner == {
        "ruc": fx.NATURAL_RUC[:4] + "*********",
        "name": "Persona natural",
        "kind": "natural_person",
    }


def test_unidentified_winner_block_has_only_the_label(client: TestClient) -> None:
    winner = client.get(f"{API}/processes/{fx.OCID_NORUC}").json()["winner"]
    assert set(winner) == {"ruc", "name", "kind"} and winner["kind"] == "unknown"


def test_company_winner_keeps_its_profile(client: TestClient) -> None:
    winner = client.get(f"{API}/processes/{fx.OCID_COMPANY}").json()["winner"]
    assert winner["n_wins"] == 2 and winner["total_awarded"] == 1200.0


# --- 6. dossier rate limit and no traces


def test_dossier_builds_without_llm_or_traces(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list = []
    _fake_builder(monkeypatch, {"summary_es": "ok"}, seen)
    assert client.get(f"{DIRECT}/dossier").status_code == 200
    assert seen == [{"use_llm": False, "write_traces": False}]


def test_dossier_endpoint_is_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from veedor.api import security

    monkeypatch.setattr(security.dossier_rate_limiter, "limit", 2)
    security.dossier_rate_limiter.reset()
    _fake_builder(monkeypatch, {"summary_es": "ok"})
    codes = [client.get(f"{DIRECT}/dossier").status_code for _ in range(4)]
    security.dossier_rate_limiter.reset()
    assert codes == [200, 200, 429, 429]


def test_default_service_can_skip_traces(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from veedor.core.settings import Settings
    from veedor.use_cases import build_dossier

    monkeypatch.setattr(build_dossier, "get_settings", lambda: Settings(data_dir=tmp_path))
    assert build_dossier.default_service(use_llm=False, write_traces=False)._agent._traces is None
    assert build_dossier.default_service(use_llm=False)._agent._traces is not None
