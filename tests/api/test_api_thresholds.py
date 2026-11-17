"""Threshold context endpoints on a small synthetic lake: values, nulls, injection payloads, GET only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import duckdb
import pytest
from fastapi.testclient import TestClient
from test_api_security import PAYLOADS

from veedor.api.deps import get_reader
from veedor.api.main import create_app
from veedor.infrastructure.lake.reader import LakeReader
from veedor.infrastructure.lake.threshold_context import build_threshold_context

API = "/api/v1"
T_2023 = 63005.73  # menor cuantia / cotizacion, goods and services, 2023 (verified table)


def _row(ocid, year, method, group, category, budget, buyer="b1"):
    return (ocid, year, method, group, category, budget, None, buyer, "BUYER " + buyer)


ROWS = [
    _row("ocds-5wno2w-T-1", 2023, "Menor Cuantía", "competitive", "goods", 62500.0),
    _row("ocds-5wno2w-T-2", 2023, "Menor Cuantía", "competitive", "goods", 40000.0),
    _row("ocds-5wno2w-T-3", 2023, "Cotización", "competitive", "goods", 90000.0),
    _row("ocds-5wno2w-T-4", 2025, "Menor Cuantía", "competitive", "goods", 62500.0),
    _row("ocds-5wno2w-T-5", 2023, "Contratacion directa", "direct", "goods", 62500.0),
    _row("ocds-5wno2w-T-6", 2023, "Licitación", "competitive", "goods", 9_000_000.0),
    _row("ocds-5wno2w-T-7", 2023, "Menor Cuantía", "competitive", "goods", None),
]


@pytest.fixture
def threshold_client(tmp_path: Path) -> Iterator[TestClient]:
    lake, marts = tmp_path / "lake", tmp_path / "marts"
    lake.mkdir()
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE processes (ocid VARCHAR, year INTEGER, method VARCHAR, method_group VARCHAR, "
        "category VARCHAR, budget DOUBLE, award_total DOUBLE, buyer_ruc VARCHAR, buyer_name VARCHAR)"
    )
    con.executemany("INSERT INTO processes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", ROWS)
    con.execute("COPY processes TO ? (FORMAT parquet)", [str(lake / "processes.parquet")])
    build_threshold_context(lake, marts, n_boot=20)
    app = create_app()
    app.dependency_overrides[get_reader] = lambda: LakeReader(lake, marts, refresh_interval=0)
    with TestClient(app) as client:
        yield client


def test_stats_lists_verified_thresholds_with_sources(threshold_client: TestClient) -> None:
    body = threshold_client.get(f"{API}/stats/thresholds").json()
    years = {i["year"] for i in body["items"]}
    assert 2025 not in years and {2015, 2023, 2026} <= years
    item = next(
        i for i in body["items"] if i["year"] == 2023 and i["threshold_code"] == "GS_MENOR_COTIZACION"
    )
    assert item["threshold_usd"] == T_2023
    assert item["source_url"].startswith("https://portal.compraspublicas.gob.ec/")
    assert item["n_band_below"] == 1 and item["n_band_above"] == 0
    assert item["bunching"]["status"] == "insufficient_data"  # far below 200 processes
    assert "2025" in body["excluded_years"]
    assert any("no cambia ningún puntaje" in n for n in body["notes"])


def test_process_just_below(threshold_client: TestClient) -> None:
    body = threshold_client.get(f"{API}/processes/ocds-5wno2w-T-1/threshold").json()
    assert body["applicable"] is True and body["just_below"] is True
    assert body["threshold"]["threshold_usd"] == T_2023
    assert body["distance_to_threshold_pct"] == round((T_2023 - 62500.0) / T_2023 * 100, 2)


def test_process_far_below_is_false_not_null(threshold_client: TestClient) -> None:
    body = threshold_client.get(f"{API}/processes/ocds-5wno2w-T-2/threshold").json()
    assert body["applicable"] is True and body["just_below"] is False


@pytest.mark.parametrize(
    ("ocid", "reason"),
    [
        ("T-3", None),  # cotizacion: the next threshold above is cotizacion/licitacion
        ("T-4", "year_not_verified"),
        ("T-5", "not_competitive_procedure"),
        ("T-6", "budget_above_all_thresholds"),
        ("T-7", "no_budget"),
    ],
)
def test_process_null_cases(threshold_client: TestClient, ocid: str, reason: str | None) -> None:
    body = threshold_client.get(f"{API}/processes/ocds-5wno2w-{ocid}/threshold").json()
    if reason is None:
        assert body["applicable"] is True and body["threshold"]["code"] == "GS_COTIZACION_LICITACION"
        return
    assert body["applicable"] is False and body["reason_code"] == reason
    assert body["just_below"] is None and body["threshold"] is None


def test_unknown_process_is_404(threshold_client: TestClient) -> None:
    assert threshold_client.get(f"{API}/processes/ocds-5wno2w-nope/threshold").status_code == 404


@pytest.mark.parametrize("payload", PAYLOADS)
def test_payloads_in_ocid_path(threshold_client: TestClient, payload: str) -> None:
    response = threshold_client.get(f"{API}/processes/{quote(payload, safe='')}/threshold")
    assert response.status_code in {404, 422}
    for leak in ("Traceback", "duckdb", "SELECT ", "root:"):
        assert leak not in response.text


@pytest.mark.parametrize("payload", PAYLOADS)
def test_payloads_in_stats_query_change_nothing(threshold_client: TestClient, payload: str) -> None:
    baseline = threshold_client.get(f"{API}/stats/thresholds").json()
    response = threshold_client.get(f"{API}/stats/thresholds", params={"year": payload, "q": payload})
    assert response.status_code == 200 and response.json() == baseline


def test_get_only(threshold_client: TestClient) -> None:
    for path in ("/stats/thresholds", "/processes/ocds-5wno2w-T-1/threshold"):
        for method in ("post", "put", "delete", "patch"):
            assert getattr(threshold_client, method)(API + path).status_code in {405, 404}


def test_missing_mart_is_503(tmp_path: Path) -> None:
    app = create_app()
    app.dependency_overrides[get_reader] = lambda: LakeReader(tmp_path / "lake", tmp_path / "marts")
    with TestClient(app) as client:
        assert client.get(f"{API}/stats/thresholds").status_code == 503
