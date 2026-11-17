"""The injection payload set, the DuckDB lockdown and the OpenAPI contract for the stage-3 routes."""

from __future__ import annotations

from urllib.parse import quote

import api_fixture_data as fx
import duckdb
import pytest
from fastapi.testclient import TestClient
from test_api_security import PAYLOADS

from veedor.domain.text_match import fold
from veedor.infrastructure.lake import reader as reader_module

API = "/api/v1"
OK_OR_REJECTED = {200, 404, 422}
EXTRA_PAYLOADS = [
    *PAYLOADS,
    "\x00",
    "%",
    "_",
    "\\",
    "💥",
    "A" * 5000,
    "9" * 400,
    "-1",
    "1e999",
    "nan",
    "true; DROP",
]


def _safe(response, *, allowed=OK_OR_REJECTED) -> None:
    assert response.status_code in allowed, (response.status_code, response.text[:200])
    for leak in ("Traceback", "duckdb", "SELECT ", "etc/passwd", "root:"):
        assert leak not in response.text


@pytest.mark.parametrize("payload", EXTRA_PAYLOADS)
def test_payload_in_region(stats_client: TestClient, payload: str) -> None:
    response = stats_client.get(f"{API}/processes", params={"region": payload})
    _safe(response, allowed={422})  # nothing but the 25 known keys passes


@pytest.mark.parametrize("payload", EXTRA_PAYLOADS)
@pytest.mark.parametrize("param", ["with_signals", "min_score"])
def test_payload_in_random_parameters(stats_client: TestClient, payload: str, param: str) -> None:
    response = stats_client.get(f"{API}/processes/random", params={param: payload})
    _safe(response)
    if response.status_code == 200:  # e.g. "true; DROP" is not a bool, but "-1"... must not widen anything
        assert response.json()["ocid"].startswith("ocds-5wno2w-st-")


@pytest.mark.parametrize("payload", EXTRA_PAYLOADS)
def test_payload_in_buyer_search_text(stats_client: TestClient, payload: str) -> None:
    response = stats_client.get(f"{API}/buyers/search", params={"q": payload})
    _safe(response)
    if response.status_code == 200:
        # Plain text only: a name is returned just when it really contains every word of the payload,
        # so a payload can never widen the result (`" OR ""="` is the word "or", found in "Norte").
        tokens = fold(payload).split()
        for item in response.json()["items"]:
            assert tokens and all(token in fold(item["name"]) for token in tokens), item


@pytest.mark.parametrize("payload", EXTRA_PAYLOADS)
def test_payload_in_buyer_search_limit(stats_client: TestClient, payload: str) -> None:
    response = stats_client.get(f"{API}/buyers/search", params={"q": "municip", "limit": payload})
    _safe(response)
    if response.status_code == 200:
        assert len(response.json()["items"]) <= 10


@pytest.mark.parametrize("payload", EXTRA_PAYLOADS)
def test_payload_in_context_path(stats_client: TestClient, payload: str) -> None:
    response = stats_client.get(f"{API}/processes/{quote(payload, safe='')}/context")
    _safe(response, allowed={404, 422})


def test_payloads_change_nothing(stats_client: TestClient) -> None:
    baseline = {
        "stats": stats_client.get(f"{API}/stats/by-region").json(),
        "years": stats_client.get(f"{API}/stats/by-year").json(),
        "search": stats_client.get(f"{API}/buyers/search", params={"q": "municip"}).json(),
        "context": stats_client.get(f"{API}/processes/ocds-5wno2w-st-0001/context").json(),
        "total": stats_client.get(f"{API}/processes", params={"region": "MANABI"}).json()["total"],
    }
    for payload in PAYLOADS:
        stats_client.get(f"{API}/processes", params={"region": payload, "q": payload})
        stats_client.get(f"{API}/processes/random", params={"min_score": payload, "with_signals": payload})
        stats_client.get(f"{API}/buyers/search", params={"q": payload, "limit": payload})
        stats_client.get(f"{API}/processes/{quote(payload, safe='')}/context")
    assert baseline == {
        "stats": stats_client.get(f"{API}/stats/by-region").json(),
        "years": stats_client.get(f"{API}/stats/by-year").json(),
        "search": stats_client.get(f"{API}/buyers/search", params={"q": "municip"}).json(),
        "context": stats_client.get(f"{API}/processes/ocds-5wno2w-st-0001/context").json(),
        "total": stats_client.get(f"{API}/processes", params={"region": "MANABI"}).json()["total"],
    }


def test_new_routes_only_answer_get(stats_client: TestClient) -> None:
    for path in ("/stats/by-region", "/stats/by-year", "/processes/random", "/buyers/search", "/glossary"):
        for method in ("post", "put", "delete", "patch"):
            assert getattr(stats_client, method)(API + path).status_code in {405, 404}


def test_new_routes_carry_the_hardening_headers(stats_client: TestClient) -> None:
    for path in (
        "/stats/by-region",
        "/stats/by-year",
        "/processes/random",
        "/buyers/search?q=municip",
        "/processes/ocds-5wno2w-st-0001/context",
    ):
        response = stats_client.get(API + path)
        assert response.status_code == 200, path
        # Caching policy is asserted in test_api_http_cache.py; here only that one is always set.
        assert response.headers["cache-control"].startswith(("no-store", "public, max-age="))
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'none'" in response.headers["content-security-policy"]


# --- DuckDB lockdown: every statement a new route sends is exactly one SELECT


def test_every_new_query_is_exactly_one_select(stats_client: TestClient, monkeypatch) -> None:
    from veedor.api.deps import get_reader
    from veedor.use_cases.queries._cache import clear_all_caches

    reader = stats_client.app.dependency_overrides[get_reader]()
    sent: list[str] = []
    real = reader.fetch
    monkeypatch.setattr(reader, "fetch", lambda sql, *a, **k: sent.append(sql) or real(sql, *a, **k))
    clear_all_caches()
    for path in (
        "/stats/by-region",
        "/stats/by-year",
        "/processes/random",
        "/processes/random?with_signals=true&min_score=10.5",
        "/buyers/search?q=municip",
        "/processes/ocds-5wno2w-st-0001/context",
        "/processes?region=MANABI",
        "/processes?region=SIN_REGION&q=ST",
    ):
        assert stats_client.get(API + path).status_code in {200, 404}, path
    assert len(sent) >= 10
    for sql in sent:
        statements = duckdb.extract_statements(sql)
        assert len(statements) == 1 and statements[0].type == duckdb.StatementType.SELECT, sql
        reader_module._check_read_only(sql)


def test_user_text_never_reaches_sql_text(stats_client: TestClient, monkeypatch) -> None:
    from veedor.api.deps import get_reader

    reader = stats_client.app.dependency_overrides[get_reader]()
    sent: list[str] = []
    real = reader.fetch
    monkeypatch.setattr(reader, "fetch", lambda sql, *a, **k: sent.append(sql) or real(sql, *a, **k))
    marker = "zzmarkerzz"
    stats_client.get(f"{API}/buyers/search", params={"q": marker})
    stats_client.get(f"{API}/processes", params={"region": marker, "q": marker})
    stats_client.get(f"{API}/processes/random", params={"min_score": "12.5"})
    stats_client.get(f"{API}/processes", params={"region": "LOS RIOS"})
    assert sent and not any(marker in sql or "12.5" in sql or "LOS RIOS" in sql for sql in sent)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_text('/etc/hosts')",
        "SELECT * FROM read_csv('/etc/passwd')",
        "COPY (SELECT 1) TO '/tmp/x.csv'",
        "SELECT 1; CREATE VIEW v AS SELECT 1",
        "ATTACH '/tmp/x.db' AS x",
        "SELECT * FROM (SELECT ocid FROM processes) USING SAMPLE 1; DROP VIEW processes",
    ],
)
def test_the_reader_still_refuses_what_the_new_routes_never_send(lake_dirs, sql: str) -> None:
    from veedor.infrastructure.lake.reader import LakeReader

    reader = LakeReader(*lake_dirs)
    with pytest.raises((duckdb.Error, ValueError)):
        reader.fetch(sql, tables=("processes",))


# --- OpenAPI contract


@pytest.fixture
def schema(stats_client: TestClient) -> dict:
    return stats_client.get("/openapi.json").json()


@pytest.mark.parametrize(
    ("path", "model"),
    [
        ("/api/v1/stats/by-region", "RegionStats"),
        ("/api/v1/stats/by-year", "YearStats"),
        ("/api/v1/processes/random", "ProcessSummary"),
        ("/api/v1/buyers/search", "BuyerSearchResult"),
        ("/api/v1/processes/{ocid}/context", "ProcessContext"),
        ("/api/v1/glossary", "Glossary"),
    ],
)
def test_new_routes_are_documented_with_response_models(schema: dict, path: str, model: str) -> None:
    operation = schema["paths"][path]["get"]
    ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith(f"/{model}")
    assert operation["summary"] and operation["description"]
    assert "503" in operation["responses"] or path.endswith("/random")


def test_region_filter_lists_the_closed_set_of_keys(schema: dict) -> None:
    params = {p["name"]: p for p in schema["paths"]["/api/v1/processes"]["get"]["parameters"]}
    region = params["region"]["schema"]
    options = region.get("enum") or next(x for x in region["anyOf"] if "$ref" in x)
    if "$ref" in options:
        options = schema["components"]["schemas"][options["$ref"].rsplit("/", 1)[1]]["enum"]
    assert len(options) == 25 and "SIN_REGION" in options and "CAÑAR" in options
    assert "provincia" in params["region"]["description"].lower()


def test_user_facing_fields_have_spanish_descriptions(schema: dict) -> None:
    components = schema["components"]["schemas"]
    for name, fields in {
        "RegionStat": ["region_label", "pct_with_signal", "small_sample", "competitive_processes"],
        "YearStat": ["pct_single_bidder", "method_mix", "partial_year", "notes"],
        "BuyerHit": ["region_label", "processes_total"],
        "RatioMeasure": ["percentile", "median", "q1", "q3"],
        "TenderersContext": ["percentile", "distribution"],
    }.items():
        for field in fields:
            assert components[name]["properties"][field].get("description"), (name, field)
    assert "porcentaje" in components["RatioMeasure"]["properties"]["percentile"]["description"].lower()
    assert "menor o igual" in components["RatioMeasure"]["properties"]["percentile"]["description"]


def test_examples_use_fictional_entities(schema: dict) -> None:
    components = schema["components"]["schemas"]
    assert components["BuyerHit"]["properties"]["name"]["examples"] == ["GAD Municipal de Ejemplo"]
    assert components["BuyerHit"]["properties"]["ruc"]["examples"] == ["1760001230001"]
    assert fx.BUYER_NAME == "GAD Municipal de Ejemplo"


def test_glossary_tag_is_declared(schema: dict) -> None:
    assert "glosario" in {tag["name"] for tag in schema["tags"]}
