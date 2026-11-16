"""Request spans and RED metrics are keyed by route template, never by the raw path."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from veedor.infrastructure.telemetry import instrument_app

OCID = "ocds-5wno2w-LICO-GADMC-001-2023"
RUC = "1790012345001"


@pytest.fixture
def client(capture) -> TestClient:
    app = FastAPI()
    router = APIRouter()  # included with a prefix, like the real v1 router

    @router.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @router.get("/processes/{ocid}")
    def process(ocid: str) -> dict:
        return {"ocid": ocid}

    @router.get("/suppliers/{ruc}")
    def supplier(ruc: int) -> dict:  # int path param: a non-numeric value gives 422
        return {"ruc": ruc}

    @router.get("/boom")
    def boom() -> dict:
        raise RuntimeError(f"secret {RUC}")

    app.include_router(router, prefix="/api/v1")
    instrument_app(app)
    return TestClient(app, raise_server_exceptions=False)


def _routes(capture) -> set[str]:
    return {s.attributes["http.route"] for s in capture.finished_spans() if "http.route" in s.attributes}


def test_span_name_and_route_label_use_the_template(client: TestClient, capture) -> None:
    assert client.get(f"/api/v1/processes/{OCID}").status_code == 200
    (finished,) = capture.finished_spans()
    assert finished.name == "GET /api/v1/processes/{ocid}"
    assert finished.attributes["http.route"] == "/api/v1/processes/{ocid}"
    assert finished.attributes["http.response.status_code"] == 200
    assert finished.attributes["ocid"] == OCID
    routes = {a["http.route"] for n, a, _ in capture.metric_points() if n == "http.server.request.duration"}
    assert routes == {"/api/v1/processes/{ocid}"}


def test_raw_path_never_appears_in_names_attributes_or_labels(client: TestClient, capture) -> None:
    client.get(f"/api/v1/processes/{OCID}")
    client.get(f"/api/v1/suppliers/{RUC}")
    client.get(f"/api/v1/nowhere/{RUC}")  # unmatched: raw path must not become the route
    client.get(f"/api/v1/suppliers/{RUC}x")  # 422
    text = capture.everything_as_text()
    assert RUC not in text
    assert "nowhere" not in text
    # the only place the process id may appear is the `ocid` attribute
    assert text.replace(f"ocid={OCID}", "").count(OCID) == 0
    assert "unmatched" in _routes(capture)


def test_error_statuses_are_recorded(client: TestClient, capture) -> None:
    assert client.get(f"/api/v1/suppliers/{RUC}x").status_code == 422
    assert client.get("/api/v1/missing").status_code == 404
    assert client.get("/api/v1/boom").status_code == 500
    by_status = {s.attributes["http.response.status_code"]: s for s in capture.finished_spans()}
    assert set(by_status) == {422, 404, 500}
    assert by_status[500].status.status_code.name == "ERROR"
    assert by_status[404].status.status_code.name == "UNSET"
    assert "secret" not in capture.everything_as_text()


def test_health_is_excluded_from_traces_and_metrics(client: TestClient, capture) -> None:
    assert client.get("/api/v1/health").status_code == 200
    assert capture.finished_spans() == ()
    assert capture.metric_points() == []


def test_requests_pass_through_untouched_when_disabled(capture) -> None:
    from veedor.infrastructure.telemetry import shutdown_telemetry

    app = FastAPI()

    @app.get("/x")
    def x() -> dict:
        return {"ok": 1}

    instrument_app(app)
    shutdown_telemetry()
    assert TestClient(app).get("/x").json() == {"ok": 1}
