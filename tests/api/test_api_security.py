"""Injection payloads, hardening headers, size limit and rate limit."""

from __future__ import annotations

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

API = "/api/v1"

PAYLOADS = [
    "' OR 1=1 --",
    "'; DROP TABLE reviews; --",
    "%' UNION SELECT * FROM read_text('/etc/passwd') --",
    "../../../etc/passwd",
    "..%2f..%2fetc%2fpasswd",
    "risk_score; DROP TABLE reviews",
    "1; ATTACH '/tmp/x.db' AS x",
    '" OR ""="',
    "%00",
    "${jndi:ldap://x}",
]


def _never_server_error(response) -> None:
    assert response.status_code < 500, response.text
    assert "Traceback" not in response.text and "duckdb" not in response.text.lower()
    assert "SELECT" not in response.text


@pytest.mark.parametrize("payload", PAYLOADS)
@pytest.mark.parametrize("param", ["year", "method", "buyer_ruc", "signal", "min_score", "q", "sort", "page"])
def test_payload_in_every_list_parameter(client: TestClient, payload: str, param: str) -> None:
    response = client.get(f"{API}/processes", params={param: payload})
    _never_server_error(response)
    if response.status_code == 200:
        assert response.json()["total"] <= 4  # a payload never widens the result set beyond the data


@pytest.mark.parametrize("payload", PAYLOADS)
def test_payload_in_path_parameters(client: TestClient, payload: str) -> None:
    for template in (
        "/processes/{}",
        "/processes/{}/dossier",
        "/suppliers/{}",
        "/buyers/{}",
        "/processes/{}/reviews",
    ):
        response = client.get(API + template.format(payload))
        _never_server_error(response)
        assert response.status_code in {404, 422}


def test_path_params_have_strict_formats(client: TestClient) -> None:
    assert client.get(f"{API}/suppliers/123").status_code == 422
    assert client.get(f"{API}/suppliers/{'9' * 14}").status_code == 422
    assert client.get(f"{API}/processes/not-an-ocid").status_code == 422
    assert client.get(f"{API}/processes/ocds-5wno2w-" + "a" * 121).status_code == 422


def test_wildcard_abuse_in_q_matches_nothing(client: TestClient) -> None:
    for q in ("%", "_", "%%%%", "\\", "\\%", "_%_"):
        body = client.get(f"{API}/processes", params={"q": q}).json()
        assert body["total"] == 0, q
    assert client.get(f"{API}/processes", params={"q": "x" * 81}).status_code == 422


def test_injected_sort_is_rejected_not_executed(client: TestClient) -> None:
    for sort in (
        "risk_score; DROP TABLE reviews",
        "risk_score,ocid",
        "(select 1)",
        "-risk_score desc",
        "RISK_SCORE",
    ):
        response = client.get(f"{API}/processes", params={"sort": sort})
        assert response.status_code == 422
        assert "DROP" not in response.json()["error"]["message"]


def test_reviews_table_survives_every_payload(db_client: TestClient, migrated_engine) -> None:
    for payload in PAYLOADS:
        db_client.get(f"{API}/processes", params={"q": payload, "method": payload, "sort": payload})
        db_client.get(f"{API}/processes/{payload}/reviews")
        db_client.post(
            f"{API}/processes/{fx.OCID_COMPANY}/reviews",
            json={"status": "pending", "note": payload, "reviewer": payload},
            headers=fx.REVIEW_HEADERS,
        )
        db_client.post(
            f"{API}/processes/{payload}/reviews", json={"status": "pending"}, headers=fx.REVIEW_HEADERS
        )
    assert "reviews" in inspect(migrated_engine).get_table_names()
    notes = [r["note"] for r in db_client.get(f"{API}/processes/{fx.OCID_COMPANY}/reviews").json()]
    assert "'; DROP TABLE reviews; --" in notes  # stored verbatim as data, never executed


def test_unexpected_errors_do_not_leak_details(lake_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient as Client

    from veedor.api.deps import get_lake
    from veedor.api.main import create_app

    class Exploding:
        def fetch(self, *args, **kwargs):
            raise RuntimeError("SELECT secret FROM internal_table password=hunter2")

        def has_table(self, name: str) -> bool:
            return True

        def availability(self) -> dict:
            return {}

    app = create_app()
    app.dependency_overrides[get_lake] = Exploding
    response = Client(app, raise_server_exceptions=False).get(f"{API}/stats")
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "Error interno del servidor."}}
    assert "hunter2" not in response.text


def test_security_headers_present(client: TestClient) -> None:
    response = client.get(f"{API}/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["content-security-policy"]


def test_cors_only_allows_configured_origin(client: TestClient) -> None:
    allowed = client.get(f"{API}/health", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    denied = client.get(f"{API}/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in denied.headers


def test_oversized_body_is_rejected(client: TestClient) -> None:
    body = '{"status":"pending","note":"' + "a" * 20000 + '"}'
    response = client.post(
        f"{API}/processes/{fx.OCID_COMPANY}/reviews",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413 and response.json()["error"]["code"] == "payload_too_large"


def test_review_post_is_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from veedor.api import security

    monkeypatch.setattr(security.review_rate_limiter, "limit", 3)
    # 503 (no database in this client) still counts: the limiter runs before the handler
    statuses = [
        client.post(
            f"{API}/processes/{fx.OCID_COMPANY}/reviews", json={"status": "bogus"}, headers=fx.REVIEW_HEADERS
        ).status_code
        for _ in range(5)
    ]
    assert statuses[:3] == [422] * 3 and statuses[3:] == [429, 429]
    assert client.get(f"{API}/processes").status_code == 200  # the review limit does not touch reads


# --- phase 3 hardening


@pytest.mark.parametrize("page", ["99999999999999999999", "9223372036854775807", "1000001", "0", "-1"])
def test_page_is_bounded(client: TestClient, page: str) -> None:
    response = client.get(f"{API}/processes", params={"page": page})
    assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"


def test_page_times_page_size_is_bounded(client: TestClient) -> None:
    response = client.get(f"{API}/processes", params={"page": 20000, "page_size": 100})
    assert response.status_code == 422
    assert client.get(f"{API}/processes", params={"page": 10000, "page_size": 100}).status_code == 200


def test_path_params_reject_unicode_digits(client: TestClient) -> None:
    arabic_indic = "١٢٣٤٥٦٧٨٩٠١٢٣"  # 13 Unicode decimal digits
    assert client.get(f"{API}/suppliers/{arabic_indic}").status_code == 422
    assert client.get(f"{API}/buyers/{arabic_indic}").status_code == 422
    assert client.get(f"{API}/processes", params={"buyer_ruc": arabic_indic}).status_code == 422


def test_trailing_slash_is_not_redirected(client: TestClient) -> None:
    response = client.get(f"{API}/processes/", headers={"Host": "evil.example"}, follow_redirects=False)
    assert response.status_code not in {301, 302, 307, 308}
    assert "location" not in response.headers


def test_docs_use_pinned_assets_with_integrity(client: TestClient) -> None:
    html = client.get("/docs").text
    assert "swagger-ui-dist@5.17.14" in html
    assert html.count('integrity="sha384-') == 2
    assert client.get("/redoc").status_code == 404


def test_docs_can_be_disabled(lake_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    from veedor.api.main import create_app
    from veedor.core.settings import Settings

    monkeypatch.setattr("veedor.api.main.get_settings", lambda: Settings(docs_enabled=False))
    with TestClient(create_app()) as disabled:
        assert disabled.get("/docs").status_code == 404
        assert disabled.get("/openapi.json").status_code == 404
        assert disabled.get(f"{API}/health").status_code == 200


def test_ci_workflow_has_minimal_permissions() -> None:
    from pathlib import Path

    workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text()
    assert "permissions:\n  contents: read" in workflow


def test_compose_binds_ports_to_loopback() -> None:
    from pathlib import Path

    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text()
    published = [
        line.strip() for line in compose.splitlines() if line.strip().startswith('- "') and ":" in line
    ]
    ports = [line for line in published if line.count(":") >= 2 and line.rstrip('"').split(":")[-1].isdigit()]
    assert ports and all(p.startswith('- "127.0.0.1:') for p in ports)
