"""HTTP caching: validators, conditional requests, route classes, Vary and masking."""

from __future__ import annotations

import os
from pathlib import Path

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient

from veedor.api import http_cache
from veedor.api.deps import get_reader
from veedor.api.main import create_app
from veedor.infrastructure.lake.reader import LakeReader

API = "/api/v1"
AGGREGATE = "public, max-age=300, stale-while-revalidate=86400"
PER_PROCESS = "public, max-age=60"
LISTING = "public, max-age=30"
ORIGIN = "http://localhost:3000"

CACHEABLE = [
    (f"{API}/stats", AGGREGATE),
    (f"{API}/stats/by-region", AGGREGATE),
    (f"{API}/stats/by-year", AGGREGATE),
    (f"{API}/stats/thresholds", AGGREGATE),
    (f"{API}/signals", AGGREGATE),
    (f"{API}/glossary", AGGREGATE),
    (f"{API}/processes?page_size=5", LISTING),
    (f"{API}/buyers/search?q=municip", LISTING),
    (f"{API}/processes/{fx.OCID_COMPANY}", PER_PROCESS),
    (f"{API}/processes/{fx.OCID_COMPANY}/provenance", PER_PROCESS),
    (f"{API}/processes/{fx.OCID_COMPANY}/dossier", PER_PROCESS),
    (f"{API}/suppliers/{fx.COMPANY_RUC}", PER_PROCESS),
    (f"{API}/buyers/{fx.BUYER_RUC}", PER_PROCESS),
]
SECURITY = ("x-content-type-options", "x-frame-options", "referrer-policy", "content-security-policy")


@pytest.fixture
def cclient(stats_dirs: tuple[Path, Path]):
    """API over the larger statistics lake (the aggregates need it); stateless reader per call."""
    app = create_app()
    app.dependency_overrides[get_reader] = lambda: LakeReader(*stats_dirs, refresh_interval=0)
    with TestClient(app) as test_client:
        yield test_client


def _stats_urls() -> list[tuple[str, str]]:
    return [
        (f"{API}/stats/by-region", AGGREGATE),
        (f"{API}/stats/by-year", AGGREGATE),
        (f"{API}/signals", AGGREGATE),
        (f"{API}/glossary", AGGREGATE),
        (f"{API}/processes?page_size=5", LISTING),
        (f"{API}/buyers/search?q=municip", LISTING),
        (f"{API}/processes/ocds-5wno2w-st-0001/context", PER_PROCESS),
    ]


@pytest.mark.parametrize(("url", "cache_control"), _stats_urls())
def test_cacheable_route_has_etag_class_and_vary(cclient: TestClient, url: str, cache_control: str) -> None:
    response = cclient.get(url)
    assert response.status_code == 200, url
    assert response.headers["cache-control"] == cache_control
    assert response.headers["etag"].startswith('W/"')
    assert response.headers["vary"] == "Origin"
    assert cclient.get(url).headers["etag"] == response.headers["etag"]


@pytest.mark.parametrize(("url", "cache_control"), CACHEABLE)
def test_conditional_request_gets_an_empty_304_with_the_same_headers(
    client: TestClient, url: str, cache_control: str
) -> None:
    first = client.get(url)
    if first.status_code != 200:  # a mart this small fixture lacks (aggregates are covered above)
        pytest.skip(f"{url}: {first.status_code}")
    etag = first.headers["etag"]
    second = client.get(url, headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["etag"] == etag
    assert second.headers["cache-control"] == cache_control
    assert second.headers["vary"] == "Origin"
    for name in SECURITY:
        assert second.headers[name] == first.headers[name], name


def test_if_none_match_forms(cclient: TestClient) -> None:
    url = f"{API}/stats/by-year"
    etag = cclient.get(url).headers["etag"]
    strong = etag[2:]
    for header in (etag, strong, f'"zzz", {etag}'):
        assert cclient.get(url, headers={"If-None-Match": header}).status_code == 304, header
    # `*` does not prove the resource exists, so it never short-circuits a signature-mode route.
    for header in ("*", '"zzz"', "", "W/"):
        assert cclient.get(url, headers={"If-None-Match": header}).status_code == 200, header


def test_a_304_does_not_run_the_route(cclient: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"{API}/stats/by-year"
    etag = cclient.get(url).headers["etag"]

    def boom(*_args, **_kwargs):
        raise AssertionError("the route ran for a conditional request that matched")

    monkeypatch.setattr("veedor.api.v1.stats.year_stats.get_year_stats", boom)
    assert cclient.get(url, headers={"If-None-Match": etag}).status_code == 304


def test_etag_is_the_same_on_two_independent_workers(stats_dirs: tuple[Path, Path]) -> None:
    clients = []
    for _ in range(2):  # separate app, separate reader, separate caches: like two uvicorn workers
        app = create_app()
        app.dependency_overrides[get_reader] = lambda: LakeReader(*stats_dirs)
        clients.append(TestClient(app))
    for url, _ in _stats_urls():
        assert clients[0].get(url).headers["etag"] == clients[1].get(url).headers["etag"], url


def test_etag_changes_when_the_data_build_changes(
    cclient: TestClient, stats_dirs: tuple[Path, Path]
) -> None:
    url = f"{API}/stats/by-year"
    old = cclient.get(url).headers["etag"]
    marts = stats_dirs[1]
    summary = marts / "build_summary.json"
    summary.write_text("{}") if not summary.exists() else None
    stamp = summary.stat().st_mtime_ns + 5_000_000_000
    os.utime(summary, ns=(stamp, stamp))
    fresh = cclient.get(url, headers={"If-None-Match": old})
    assert fresh.status_code == 200
    assert fresh.headers["etag"] != old
    assert cclient.get(url, headers={"If-None-Match": fresh.headers["etag"]}).status_code == 304


def test_etag_changes_with_the_api_version(cclient: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"{API}/stats/by-region"
    old = cclient.get(url).headers["etag"]
    monkeypatch.setattr(http_cache, "VERSION", "99.0.0")
    assert cclient.get(url).headers["etag"] != old


def test_query_is_normalised_but_different_queries_differ(cclient: TestClient) -> None:
    a = cclient.get(f"{API}/processes?page_size=5&sort=-risk_score").headers["etag"]
    b = cclient.get(f"{API}/processes?sort=-risk_score&page_size=5").headers["etag"]
    c = cclient.get(f"{API}/processes?page_size=6&sort=-risk_score").headers["etag"]
    assert a == b != c
    other_path = cclient.get(f"{API}/stats/by-year").headers["etag"]
    assert other_path not in {a, c}


@pytest.mark.parametrize(
    "url",
    [
        f"{API}/health",
        f"{API}/meta",
        f"{API}/processes/random",
        f"{API}/processes/ocds-5wno2w-st-0001/quotes",
        f"{API}/processes/ocds-5wno2w-st-0001/reviews",
        f"{API}/processes/ocds-5wno2w-st-0001/investigation",
        f"{API}/processes/not-an-ocid",
        f"{API}/processes/ocds-5wno2w-missing",
        f"{API}/processes?page=0",
        f"{API}/suppliers/123",
        f"{API}/nothing-here",
    ],
)
def test_excluded_routes_stay_no_store_without_etag(cclient: TestClient, url: str) -> None:
    response = cclient.get(url, headers={"If-None-Match": "*"})
    assert response.status_code != 304
    assert response.headers["cache-control"] == "no-store"
    assert "etag" not in response.headers


def test_writes_and_auth_requests_are_never_cached(cclient: TestClient) -> None:
    for method in ("post", "put", "delete"):
        response = getattr(cclient, method)(f"{API}/stats/by-region")
        assert response.headers["cache-control"] == "no-store"
        assert "etag" not in response.headers
    ask = cclient.post(f"{API}/processes/ocds-5wno2w-st-0001/ask", json={"question": "hola"})
    assert ask.headers["cache-control"] == "no-store" and "etag" not in ask.headers
    headers = {"Authorization": "Bearer x", "If-None-Match": "*"}
    authed = cclient.get(f"{API}/stats/by-region", headers=headers)
    assert authed.status_code == 200
    assert authed.headers["cache-control"] == "no-store" and "etag" not in authed.headers


def test_vary_origin_on_every_cacheable_response_and_cors_is_not_replayed(cclient: TestClient) -> None:
    url = f"{API}/stats/by-year"
    plain = cclient.get(url)
    allowed = cclient.get(url, headers={"Origin": ORIGIN})
    denied = cclient.get(url, headers={"Origin": "https://evil.example"})
    for response in (plain, allowed, denied):
        assert response.headers["vary"] == "Origin"  # one token, even when CORS also names it
        assert response.headers["etag"] == plain.headers["etag"]
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert "access-control-allow-origin" not in plain.headers
    assert "access-control-allow-origin" not in denied.headers
    etag = plain.headers["etag"]
    cond_allowed = cclient.get(url, headers={"Origin": ORIGIN, "If-None-Match": etag})
    cond_denied = cclient.get(url, headers={"Origin": "https://evil.example", "If-None-Match": etag})
    assert cond_allowed.status_code == cond_denied.status_code == 304
    assert cond_allowed.headers["access-control-allow-origin"] == ORIGIN
    assert "access-control-allow-origin" not in cond_denied.headers
    assert cond_allowed.headers["vary"] == cond_denied.headers["vary"] == "Origin"


@pytest.mark.parametrize("suffix", ["", "/dossier", "/provenance"])
def test_natural_person_never_unmasked_on_cached_or_304_paths(client: TestClient, suffix: str) -> None:
    url = f"{API}/processes/{fx.OCID_NATURAL}{suffix}"
    secrets = (fx.NATURAL_NAME, fx.NATURAL_RUC)
    first = client.get(url)
    if first.status_code != 200:
        pytest.skip(f"{url}: {first.status_code}")
    for _ in range(2):  # the second call is served after every in-memory cache is warm
        warm = client.get(url)
        assert warm.status_code == 200
        assert not any(value in warm.text for value in secrets)
        assert warm.headers["etag"] == first.headers["etag"]
    conditional = client.get(url, headers={"If-None-Match": first.headers["etag"]})
    assert conditional.status_code == 304 and conditional.content == b""
    assert not any(value in str(conditional.headers) for value in secrets)


def test_natural_person_buyer_and_supplier_stay_hidden_and_uncached(client: TestClient) -> None:
    for url in (f"{API}/suppliers/{fx.NATURAL_RUC}", f"{API}/buyers/{fx.NATURAL_BUYER_RUC}"):
        response = client.get(url, headers={"If-None-Match": "*"})  # `*` must not turn a 404 into a 304
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store" and "etag" not in response.headers


def test_route_table_classes() -> None:
    assert http_cache.rule_for(f"{API}/processes/random") is None
    assert http_cache.rule_for(f"{API}/processes/ocds-x/ask") is None
    assert http_cache.rule_for(f"{API}/processes/ocds-x/quotes") is None
    assert http_cache.rule_for(f"{API}/processes/ocds-x/similar").mode == "body"
    assert http_cache.rule_for(f"{API}/buyers/search").cache_control == LISTING
    assert http_cache.rule_for(f"{API}/buyers/1760004060001").cache_control == PER_PROCESS
    assert http_cache.rule_for("/openapi.json") is None
