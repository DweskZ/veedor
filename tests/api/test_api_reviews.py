from __future__ import annotations

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

API = "/api/v1"
OCID = fx.OCID_COMPANY
URL = f"{API}/processes/{OCID}/reviews"
HEADERS = fx.REVIEW_HEADERS


def test_review_round_trip(db_client: TestClient) -> None:
    created = db_client.post(
        URL,
        json={"status": "confirmed_signal", "note": "  Revisado  ", "reviewer": "analista.1"},
        headers=HEADERS,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["id"] > 0 and body["ocid"] == OCID and body["note"] == "Revisado"
    assert body["status"] == "confirmed_signal" and body["created_at"]

    db_client.post(URL, json={"status": "dismissed"}, headers=HEADERS)
    listing = db_client.get(URL).json()
    assert [r["status"] for r in listing] == ["dismissed", "confirmed_signal"]  # newest first
    assert db_client.get(f"{API}/processes/{fx.OCID_NATURAL}/reviews").json() == []


def test_review_validation(db_client: TestClient) -> None:
    assert db_client.post(URL, json={"status": "guilty"}, headers=HEADERS).status_code == 422
    assert db_client.post(URL, json={}, headers=HEADERS).status_code == 422
    assert (
        db_client.post(URL, json={"status": "pending", "note": "x" * 2001}, headers=HEADERS).status_code
        == 422
    )
    assert (
        db_client.post(URL, json={"status": "pending", "reviewer": "x" * 121}, headers=HEADERS).status_code
        == 422
    )


def test_note_is_stored_as_plain_text_and_returned_escaped(db_client: TestClient) -> None:
    note = '<script>alert("x")</script> ñ'
    response = db_client.post(URL, json={"status": "pending", "note": note}, headers=HEADERS)
    assert response.json()["note"] == note
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_review_endpoints_return_503_when_database_is_down(no_db_client: TestClient) -> None:
    post = no_db_client.post(URL, json={"status": "pending"}, headers=HEADERS)
    assert post.status_code == 503 and post.json()["error"]["code"] == "review_store_unavailable"
    assert no_db_client.get(URL).status_code == 503
    assert no_db_client.get(f"{API}/processes").status_code == 200  # the rest keeps working
    assert no_db_client.get(f"{API}/stats").status_code == 200


# --- item 7: disabled by default, token, existence, control characters, wording, masking, meta


def test_reviews_are_disabled_by_default(default_client: TestClient) -> None:
    response = default_client.post(URL, json={"status": "pending"}, headers=HEADERS)
    assert response.status_code == 403 and response.json()["error"]["code"] == "reviews_disabled"
    assert default_client.get(URL).json() == []  # no database access needed while disabled
    assert default_client.get(f"{API}/meta").json()["reviews_enabled"] is False


def test_enabled_flag_without_token_keeps_posting_disabled(
    lake_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    from veedor.api.deps import ReviewPolicy, get_review_policy
    from veedor.api.main import create_app

    app = create_app()
    app.dependency_overrides[get_review_policy] = lambda: ReviewPolicy(enabled=True, token=None)
    with TestClient(app) as client:
        response = client.post(URL, json={"status": "pending"}, headers=HEADERS)
        assert response.status_code == 403
        assert client.get(f"{API}/meta").json()["reviews_enabled"] is False


def test_policy_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from veedor.api.deps import get_review_policy
    from veedor.core.settings import Settings

    monkeypatch.setattr(
        "veedor.api.deps.get_settings", lambda: Settings(reviews_enabled=True, reviews_token=" t ")
    )
    policy = get_review_policy()
    assert policy.enabled and policy.token == "t" and policy.can_write
    monkeypatch.setattr("veedor.api.deps.get_settings", lambda: Settings(reviews_token=""))
    assert not get_review_policy().enabled and get_review_policy().token is None


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic x"}])
def test_post_requires_the_bearer_token(db_client: TestClient, headers: dict) -> None:
    response = db_client.post(URL, json={"status": "pending"}, headers=headers)
    assert response.status_code == 401 and response.json()["error"]["code"] == "invalid_token"
    assert response.headers["www-authenticate"] == "Bearer"


def test_meta_reports_reviews_enabled(client: TestClient) -> None:
    assert client.get(f"{API}/meta").json()["reviews_enabled"] is True


def test_review_for_unknown_process_is_404(db_client: TestClient) -> None:
    response = db_client.post(
        f"{API}/processes/ocds-5wno2w-nothing/reviews", json={"status": "pending"}, headers=HEADERS
    )
    assert response.status_code == 404


def test_control_characters_and_nul_are_stripped(db_client: TestClient) -> None:
    response = db_client.post(
        URL,
        json={"status": "pending", "note": "a\u0000b\u0007c​d\ne", "reviewer": "x\u0000y"},
        headers=HEADERS,
    )
    assert response.status_code == 201
    assert response.json()["note"] == "abcd\ne" and response.json()["reviewer"] == "xy"


@pytest.mark.parametrize(
    "note", ["Es un fraude evidente", "El proveedor es CORRUPTO", "actividad ilícita", "irregularidades"]
)
def test_wording_that_asserts_wrongdoing_is_rejected(
    db_client: TestClient, migrated_engine, note: str
) -> None:
    response = db_client.post(URL, json={"status": "pending", "note": note}, headers=HEADERS)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "forbidden_wording" and "señal de riesgo" in error["message"]
    with migrated_engine.connect() as connection:
        stored = connection.execute(
            text("SELECT count(*) FROM reviews WHERE note = :n"), {"n": note}
        ).scalar()
    assert stored == 0


def test_forbidden_wording_also_checked_in_reviewer(db_client: TestClient) -> None:
    response = db_client.post(URL, json={"status": "pending", "reviewer": "el culpable"}, headers=HEADERS)
    assert response.status_code == 422


def test_note_personal_data_is_masked_before_storing(db_client: TestClient, migrated_engine) -> None:
    note = f"Contactar a Ing. Pedro Salazar, cédula {fx.CEDULA}, RUC {fx.NATURAL_RUC}"
    body = db_client.post(URL, json={"status": "pending", "note": note}, headers=HEADERS).json()
    for leaked in ("Salazar", fx.CEDULA, fx.NATURAL_RUC):
        assert leaked not in body["note"]
    with migrated_engine.connect() as connection:
        stored = connection.execute(
            text("SELECT note FROM reviews WHERE id = :i"), {"i": body["id"]}
        ).scalar()
    assert stored == body["note"]
