"""Read-route rate limit: per client address, in memory; forwarded addresses; search text; memory bound."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from pathlib import Path

import api_fixture_data as fx
import pytest
import yaml
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from veedor.api.deps import ReviewPolicy, get_reader, get_review_policy
from veedor.api.main import create_app
from veedor.api.security import ReadRateLimitMiddleware, SlidingWindowRateLimiter, client_key
from veedor.core.settings import Settings, get_settings
from veedor.infrastructure.lake.reader import LakeReader

API = "/api/v1"
ROOT = Path(__file__).resolve().parents[2]
CADDY, WEB, VISITOR = "10.77.88.10", "10.77.88.20", "203.0.113.9"
TRUSTED = f"{CADDY},{WEB}"  # what deploy/compose.prod.yml gives uvicorn as FORWARDED_ALLOW_IPS


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _app(lake_dirs, monkeypatch: pytest.MonkeyPatch, *, general: int, search: int, exempt: str | None = None):
    monkeypatch.setenv("VEEDOR_READ_RATE_PER_MINUTE", str(general))
    monkeypatch.setenv("VEEDOR_READ_SEARCH_RATE_PER_MINUTE", str(search))
    if exempt is not None:
        monkeypatch.setenv("VEEDOR_READ_RATE_EXEMPT", exempt)
    get_settings.cache_clear()
    app = create_app()
    get_settings.cache_clear()
    app.dependency_overrides[get_reader] = lambda: LakeReader(*lake_dirs)
    app.dependency_overrides[get_review_policy] = lambda: ReviewPolicy(enabled=True, token=fx.REVIEW_TOKEN)
    return app


def _client(app, host: str = VISITOR) -> TestClient:
    return TestClient(app, client=(host, 50000))


def _statuses(c: TestClient, n: int, path: str = "/processes", **kwargs) -> list[int]:
    return [c.get(f"{API}{path}", **kwargs).status_code for _ in range(n)]


# --- limits, Retry-After, and what a rejection costs


def test_read_limit_triggers_with_retry_after(lake_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client(_app(lake_dirs, monkeypatch, general=3, search=100))
    assert _statuses(c, 3) == [200] * 3
    blocked = c.get(f"{API}/processes")
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(blocked.headers["retry-after"]) <= 60
    assert blocked.headers["x-content-type-options"] == "nosniff"  # outer middleware still wraps it
    cors = c.get(f"{API}/processes", headers={"Origin": "http://localhost:3000"})
    assert cors.status_code == 429 and cors.headers["access-control-allow-origin"] == "http://localhost:3000"


def _call(guard: ReadRateLimitMiddleware, host: str | None, query: bytes = b"", method: str = "GET"):
    """Run one request through the middleware alone; returns (status, headers)."""
    seen: list[dict] = []

    async def app(scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def send(message) -> None:
        if message["type"] == "http.response.start":
            seen.append({"status": message["status"], "headers": dict(message["headers"])})

    guard.app = app
    scope = {
        "type": "http",
        "method": method,
        "path": f"{API}/processes",
        "query_string": query,
        "client": (host, 1) if host else None,
    }
    asyncio.run(guard(scope, None, send))
    return seen[0]["status"], seen[0]["headers"]


def _guard(clock: Callable[[], float], **kwargs) -> ReadRateLimitMiddleware:
    kwargs.setdefault("per_minute", 3)
    kwargs.setdefault("search_per_minute", 2)
    return ReadRateLimitMiddleware(None, clock=clock, **kwargs)  # type: ignore[arg-type]


def test_retry_after_counts_down_to_the_oldest_hit_leaving_the_window() -> None:
    clock = FakeClock()
    guard = _guard(clock, per_minute=3, search_per_minute=100)
    for wait in (0, 20, 10):  # hits at t=0, 20, 30
        clock.advance(wait)
        assert _call(guard, VISITOR)[0] == 200
    clock.advance(25)  # t=55: full; the oldest hit (t=0) leaves at t=60
    status, headers = _call(guard, VISITOR)
    assert status == 429 and headers[b"retry-after"] == b"5"
    clock.advance(4)  # t=59
    assert _call(guard, VISITOR)[1][b"retry-after"] == b"1"
    clock.advance(2)  # t=61: the t=0 hit expired, 20 and 30 remain
    assert _call(guard, VISITOR)[0] == 200


def test_retry_after_is_the_longest_wait_when_both_limits_are_full() -> None:
    clock = FakeClock()
    guard = _guard(clock, per_minute=2, search_per_minute=1)
    assert _call(guard, VISITOR, b"q=obra")[0] == 200  # t=0: general 1/2, search 1/1
    clock.advance(30)
    assert _call(guard, VISITOR)[0] == 200  # t=30: general 2/2
    clock.advance(10)  # t=40: general frees at t=60 (20 s), search at t=60 (20 s)
    assert _call(guard, VISITOR, b"q=obra")[1][b"retry-after"] == b"20"
    clock.advance(25)  # t=65: general holds only the t=30 hit; search is free again
    assert _call(guard, VISITOR, b"q=obra")[0] == 200


def test_a_rejected_search_does_not_consume_general_budget() -> None:
    clock = FakeClock()
    guard = _guard(clock, per_minute=3, search_per_minute=1)
    assert _call(guard, VISITOR, b"q=obra")[0] == 200  # general 1/3, search 1/1
    assert [_call(guard, VISITOR, b"q=obra")[0] for _ in range(20)] == [429] * 20
    # Twenty rejected searches left the general count at 1: two ordinary reads still fit, the third does not.
    assert [_call(guard, VISITOR)[0] for _ in range(3)] == [200, 200, 429]
    assert guard.general is not None and len(guard.general._hits[VISITOR]) == 3  # noqa: SLF001


def test_a_rejected_general_request_does_not_consume_search_budget() -> None:
    clock = FakeClock()
    guard = _guard(clock, per_minute=3, search_per_minute=2)
    assert _call(guard, VISITOR)[0] == 200  # t=0: general 1/3
    clock.advance(30)
    assert _call(guard, VISITOR)[0] == 200  # t=30: general 2/3
    clock.advance(10)
    assert _call(guard, VISITOR, b"q=obra")[0] == 200  # t=40: general 3/3, search 1/2
    clock.advance(5)
    assert [_call(guard, VISITOR, b"q=obra")[0] for _ in range(10)] == [429] * 10  # general is full
    clock.advance(16)  # t=61: the t=0 hit left the general window; the search hit of t=40 is still in
    # Had the ten rejections been recorded as searches, search would be full (2/2) and this would be a 429.
    assert _call(guard, VISITOR, b"q=obra")[0] == 200


def test_a_rejected_request_never_grows_the_counts_beyond_the_limit() -> None:
    limiter = SlidingWindowRateLimiter(5, 60.0, clock=FakeClock())
    for _ in range(1000):
        limiter.allow("a")
    assert len(limiter._hits["a"]) == 5  # noqa: SLF001


def test_search_limit_is_stricter_than_general(lake_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client(_app(lake_dirs, monkeypatch, general=100, search=2))
    assert _statuses(c, 2, params={"q": "obra"}) == [200, 200]
    blocked = c.get(f"{API}/buyers/search", params={"q": "obra"})
    assert blocked.status_code == 429 and "retry-after" in blocked.headers
    assert c.get(f"{API}/processes").status_code == 200  # no q: only the general limit applies


def test_not_modified_responses_count(lake_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client(_app(lake_dirs, monkeypatch, general=3, search=100))
    etag = c.get(f"{API}/stats").headers["etag"]
    assert [c.get(f"{API}/stats", headers={"If-None-Match": etag}).status_code for _ in range(3)] == [
        304,
        304,
        429,
    ]


def test_health_options_and_post_are_not_counted(lake_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client(_app(lake_dirs, monkeypatch, general=1, search=1))
    assert c.get(f"{API}/processes").status_code == 200
    assert c.get(f"{API}/processes").status_code == 429
    assert _statuses(c, 5, "/health") == [200] * 5
    assert c.options(f"{API}/processes", headers={"Origin": "http://localhost:3000"}).status_code != 429
    # A POST reaches its own handler (422 for the bogus status) while the read budget stays exhausted.
    post = c.post(
        f"{API}/processes/{fx.OCID_COMPANY}/reviews", json={"status": "bogus"}, headers=fx.REVIEW_HEADERS
    )
    assert post.status_code == 422
    assert c.get(f"{API}/processes").status_code == 429


def test_post_does_not_consume_read_budget(lake_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client(_app(lake_dirs, monkeypatch, general=2, search=2))
    for _ in range(5):
        c.post(
            f"{API}/processes/{fx.OCID_COMPANY}/reviews", json={"status": "bogus"}, headers=fx.REVIEW_HEADERS
        )
    assert _statuses(c, 3) == [200, 200, 429]


def test_zero_switches_the_limits_off(lake_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client(_app(lake_dirs, monkeypatch, general=0, search=0))
    assert _statuses(c, 10, params={"q": "obra"}) == [200] * 10


def test_defaults_are_off_for_local_development_and_warn(
    lake_dirs, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    for name in (
        "VEEDOR_READ_RATE_PER_MINUTE",
        "VEEDOR_READ_SEARCH_RATE_PER_MINUTE",
        "VEEDOR_READ_RATE_EXEMPT",
    ):
        monkeypatch.delenv(name, raising=False)
    import logging

    # Another test may have run logging.config.dictConfig, which disables loggers that already existed.
    monkeypatch.setattr(logging.getLogger("veedor.api.main"), "disabled", False)
    settings = Settings(_env_file=None)
    assert (settings.read_rate_per_minute, settings.read_search_rate_per_minute) == (0, 0)
    assert settings.read_rate_exempt == []
    with caplog.at_level("WARNING", logger="veedor.api.main"):
        create_app()
    assert any("read rate limit is OFF" in r.getMessage() for r in caplog.records)
    caplog.clear()
    monkeypatch.setenv("VEEDOR_READ_RATE_PER_MINUTE", "240")
    monkeypatch.setenv("VEEDOR_READ_SEARCH_RATE_PER_MINUTE", "60")
    get_settings.cache_clear()
    with caplog.at_level("WARNING", logger="veedor.api.main"):
        create_app()
    assert not any("read rate limit is OFF" in r.getMessage() for r in caplog.records)


# --- the search text: what the limiter calls a search is what the API runs


BLANK_TEXTS = [" ", "   ", "\t", " ", " ", "   　 ", " ", "\n"]


@pytest.mark.parametrize("text", BLANK_TEXTS)
def test_blank_q_is_rejected_by_every_route_that_takes_q(client: TestClient, text: str) -> None:
    for path in ("/processes", "/buyers/search"):
        response = client.get(f"{API}{path}", params={"q": text})
        assert response.status_code == 422, (path, text)
        assert response.json()["error"]["code"] == "validation_error"


def test_q_is_trimmed_before_the_search_runs(client: TestClient) -> None:
    plain = client.get(f"{API}/processes", params={"q": "obra"}).json()
    padded = client.get(f"{API}/processes", params={"q": "  obra  "}).json()
    assert padded["total"] == plain["total"] and plain["total"] >= 1
    assert client.get(f"{API}/processes", params={"q": ""}).status_code == 422


@pytest.mark.parametrize("text", BLANK_TEXTS)
def test_blank_q_is_not_a_search_for_the_limiter(text: str) -> None:
    from urllib.parse import urlencode

    assert ReadRateLimitMiddleware.is_search(urlencode({"q": text}).encode()) is False


def test_the_limiter_reads_q_the_way_the_api_does() -> None:
    is_search = ReadRateLimitMiddleware.is_search
    assert is_search(b"q=obra") and is_search(b"q=%20obra%C2%A0")
    assert (
        not is_search(b"") and not is_search(b"q=") and not is_search(b"q=%20") and not is_search(b"q=%C2%A0")
    )
    assert not is_search(b"Q=obra") and not is_search(b"qq=obra")  # parameter names are case sensitive
    # Several values: the API uses the last one, so does the limiter.
    assert is_search(b"q=%20&q=obra") and not is_search(b"q=obra&q=%20")


def test_blank_q_requests_cost_general_budget_only(lake_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client(_app(lake_dirs, monkeypatch, general=100, search=1))
    assert _statuses(c, 10, params={"q": " "}) == [422] * 10
    assert c.get(f"{API}/processes", params={"q": "obra"}).status_code == 200  # the one search is still there


@pytest.mark.parametrize(
    "query",
    ["q=obra&q=%20", "q=%20&q=obra", "q=%C2%A0", "q=obra%20"],
)
def test_limiter_and_api_agree_on_what_is_a_search(
    lake_dirs, monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    """A request the limiter counts as a search is one the API runs (200), and the reverse (422)."""
    c = _client(_app(lake_dirs, monkeypatch, general=100, search=1000))
    status = c.get(f"{API}/processes?{query}").status_code
    assert (status == 200) == ReadRateLimitMiddleware.is_search(query.encode())


# --- who the client is: the resolved address, forwarded headers only from trusted peers


def _behind_proxies(app, peer: str) -> TestClient:
    """The app as uvicorn serves it: forwarded headers honoured only from `TRUSTED` peers."""
    return TestClient(ProxyHeadersMiddleware(app, trusted_hosts=TRUSTED), client=(peer, 50000))


def test_a_forged_forwarded_address_from_an_untrusted_peer_is_ignored(
    lake_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = _behind_proxies(_app(lake_dirs, monkeypatch, general=2, search=100), VISITOR)
    forged = [{"X-Forwarded-For": f"198.51.100.{i}", "X-Real-IP": WEB} for i in range(5)]
    codes = [c.get(f"{API}/processes", headers=h).status_code for h in forged]
    assert codes == [200, 200, 429, 429, 429]  # one bucket, the peer's, whatever the header says
    for spoofed in (WEB, CADDY):
        assert c.get(f"{API}/processes", headers={"X-Forwarded-For": spoofed}).status_code == 429


def test_a_forwarded_address_from_the_trusted_web_peer_is_used(
    lake_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(lake_dirs, monkeypatch, general=2, search=100)
    web = _behind_proxies(app, WEB)
    one, two = {"X-Forwarded-For": "198.51.100.1"}, {"X-Forwarded-For": "198.51.100.2"}
    assert [web.get(f"{API}/processes", headers=one).status_code for _ in range(3)] == [200, 200, 429]
    assert [web.get(f"{API}/processes", headers=two).status_code for _ in range(3)] == [200, 200, 429]
    # The web address itself is a different client: calls with no visitor are counted there.
    assert [web.get(f"{API}/processes").status_code for _ in range(3)] == [200, 200, 429]
    # The visitor's own direct requests (through Caddy) fall in the same bucket as its forwarded ones.
    caddy = _behind_proxies(app, CADDY)
    assert caddy.get(f"{API}/processes", headers=one).status_code == 429


def test_search_from_the_web_peer_counts_against_the_visitor(
    lake_dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(lake_dirs, monkeypatch, general=100, search=2)
    web = _behind_proxies(app, WEB)
    visitor = {"X-Forwarded-For": VISITOR}
    assert [web.get(f"{API}/processes?q=obra", headers=visitor).status_code for _ in range(3)] == [
        200,
        200,
        429,
    ]
    other = {"X-Forwarded-For": "198.51.100.77"}
    assert web.get(f"{API}/processes?q=obra", headers=other).status_code == 200  # other visitors unaffected


def test_forwarded_headers_cannot_reach_the_exemption(lake_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app(lake_dirs, monkeypatch, general=1, search=1, exempt=f'["{WEB}"]')
    outsider = _behind_proxies(app, VISITOR)
    spoof = {"X-Forwarded-For": WEB, "X-Real-IP": WEB}
    assert [outsider.get(f"{API}/processes", headers=spoof).status_code for _ in range(2)] == [200, 429]
    assert _client(app, WEB).get(f"{API}/processes").status_code == 200  # the real address is exempt
    assert _statuses(_client(app, WEB), 5) == [200] * 5


def test_exempt_addresses_and_networks_are_not_counted() -> None:
    guard = _guard(FakeClock(), per_minute=1, search_per_minute=1, exempt=[WEB, "192.168.0.0/16"])
    assert [_call(guard, WEB, b"q=x")[0] for _ in range(5)] == [200] * 5
    assert [_call(guard, "192.168.4.5", b"q=x")[0] for _ in range(5)] == [200] * 5
    assert [_call(guard, VISITOR)[0] for _ in range(2)] == [200, 429]  # not listed: counted
    assert _call(guard, "10.77.88.21")[0] == 200  # a neighbour of the exempt address is not exempt
    assert _call(guard, "10.77.88.21")[0] == 429


# --- address spelling


def test_client_key_normalises_address_spellings() -> None:
    assert client_key("::ffff:203.0.113.9") == "203.0.113.9"
    assert client_key("::FFFF:203.0.113.9") == "203.0.113.9"
    assert client_key("2001:db8:0:0:0:0:0:1") == client_key("2001:DB8::1") == "2001:db8::1"
    assert client_key("203.0.113.9") == "203.0.113.9"
    assert client_key(None) == client_key("") == "unknown"
    assert client_key("not-an-ip") == "not-an-ip"


def test_mapped_and_plain_spellings_share_one_bucket_and_one_exemption() -> None:
    guard = _guard(FakeClock(), per_minute=1, search_per_minute=1, exempt=[WEB])
    assert _call(guard, VISITOR)[0] == 200
    assert _call(guard, f"::ffff:{VISITOR}")[0] == 429
    assert [_call(guard, f"::ffff:{WEB}")[0] for _ in range(3)] == [200] * 3
    assert _call(guard, None)[0] == 200 and _call(guard, None)[0] == 429  # no client at all: one "unknown"


# --- exemption list validation


@pytest.mark.parametrize(
    "value", ["10.77.88.20/8", "10.77.88.1/24", "2001:db8::1/64", "0.0.0.0/0", "::/0", "x", ""]
)
def test_unsafe_exempt_entries_stop_the_api_at_start(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    with pytest.raises(ValueError):
        Settings(read_rate_exempt=[value])
    with pytest.raises(ValueError):
        ReadRateLimitMiddleware(None, per_minute=1, search_per_minute=1, exempt=[value])  # type: ignore[arg-type]
    monkeypatch.setenv("VEEDOR_READ_RATE_EXEMPT", json.dumps([value]))
    with pytest.raises(ValueError):
        Settings()


def test_canonical_exempt_entries_are_accepted() -> None:
    entries = [WEB, f"{WEB}/32", "10.77.88.0/24", "2001:db8::/64", "::1"]
    assert Settings(read_rate_exempt=entries).read_rate_exempt == entries
    assert Settings(read_rate_exempt=[]).read_rate_exempt == []


# --- memory bound


def test_the_key_cap_is_never_exceeded_and_never_blocks_a_new_client() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(5, 60.0, max_keys=3, clock=clock)
    for i in range(50):  # a flood of distinct addresses
        assert limiter.allow(f"198.51.100.{i}") is True  # every new client is admitted
        assert limiter.tracked_keys() <= 3
    assert limiter.tracked_keys() == 3


def test_at_the_cap_expired_clients_go_first_then_the_least_recently_active() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(1, 60.0, max_keys=3, clock=clock)
    for key in ("a", "b", "c"):
        limiter.allow(key)
        clock.advance(1)
    limiter.is_full("a")  # reading does not refresh activity
    limiter.allow("d")  # at the cap and nothing expired: the least recently active ("a") is evicted
    assert limiter.allow("a") is True  # its count restarted ...
    assert limiter.allow("c") is False  # ... while a client that was kept is still limited
    clock.advance(100)  # everything above has expired
    limiter.allow("e")
    assert limiter.tracked_keys() == 1  # expired clients were dropped, not evicted one by one


def test_idle_clients_are_swept(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(5, 60.0, max_keys=10_000, clock=clock)
    for i in range(300):
        limiter.allow(f"k{i}")
    assert limiter.tracked_keys() == 300
    clock.advance(61)
    for _ in range(1024):  # the periodic sweep runs every 1024 calls
        limiter.allow("busy")
    assert limiter.tracked_keys() == 1


def test_a_client_over_the_limit_stays_limited_at_the_cap() -> None:
    limiter = SlidingWindowRateLimiter(2, 60.0, max_keys=2, clock=FakeClock())
    assert [limiter.allow("a") for _ in range(3)] == [True, True, False]
    limiter.allow("b")
    assert limiter.allow("a") is False  # "a" stays tracked as long as it is the most recently active


# --- deploy/compose.prod.yml: the pinned addresses and the trusted-proxy list agree


def _prod_compose() -> dict:
    return yaml.safe_load((ROOT / "deploy" / "compose.prod.yml").read_text())


def _pinned(service: dict) -> str:
    return service["networks"]["internal"]["ipv4_address"]


def test_prod_compose_trusts_exactly_caddy_and_web() -> None:
    compose = _prod_compose()
    services = compose["services"]
    caddy, web = _pinned(services["caddy"]), _pinned(services["web"])
    assert (caddy, web) == (CADDY, WEB)  # the constants the tests above use are the deployed ones
    allowed = {item.strip() for item in services["api"]["environment"]["FORWARDED_ALLOW_IPS"].split(",")}
    assert allowed == {caddy, web}  # no wildcard, no network, nothing else
    import ipaddress

    subnet = ipaddress.ip_network(compose["networks"]["internal"]["ipam"]["config"][0]["subnet"])
    assert all(ipaddress.ip_address(a) in subnet for a in allowed)
    assert caddy != web


def test_prod_compose_sets_the_limits_explicitly_and_exempts_nobody() -> None:
    env = _prod_compose()["services"]["api"]["environment"]
    assert json.loads(env["VEEDOR_READ_RATE_EXEMPT"]) == []
    assert re.fullmatch(r"\$\{VEEDOR_READ_RATE_PER_MINUTE:-[1-9]\d*\}", env["VEEDOR_READ_RATE_PER_MINUTE"])
    assert re.fullmatch(
        r"\$\{VEEDOR_READ_SEARCH_RATE_PER_MINUTE:-[1-9]\d*\}", env["VEEDOR_READ_SEARCH_RATE_PER_MINUTE"]
    )
    assert "VEEDOR_READ_RATE_MAX_KEYS" in env
    # The values compose would use must be accepted by the settings.
    Settings(read_rate_exempt=json.loads(env["VEEDOR_READ_RATE_EXEMPT"]))


def test_caddy_sets_the_forwarded_address_itself_toward_web() -> None:
    caddyfile = (ROOT / "deploy" / "Caddyfile").read_text()
    web_block = caddyfile[caddyfile.index("reverse_proxy web:3000") :]
    assert re.search(r"header_up\s+X-Forwarded-For\s+\{remote_host\}", web_block)
    assert "trusted_proxies static\n" in caddyfile  # no trusted range: a client-supplied header is discarded
