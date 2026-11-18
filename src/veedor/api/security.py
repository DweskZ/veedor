"""Hardening: security headers, request size limit and a small in-memory rate limiter."""

from __future__ import annotations

import ipaddress
import math
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from threading import Lock

from fastapi import HTTPException, Request
from starlette.datastructures import QueryParams
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from veedor.api.params import trim_query_text
from veedor.core.settings import parse_exempt_networks

MAX_BODY_BYTES = 16 * 1024
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
# The interactive docs load scripts and styles from a CDN, so they get a relaxed policy.
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


def _merge_vary(headers: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    """One `Vary` header without repeated tokens (CORS and the cache middleware both name `Origin`)."""
    values = [v.decode("latin-1") for k, v in headers if k.lower() == b"vary"]
    if len(values) < 2 and not any("," in v for v in values):
        return headers
    tokens: dict[str, str] = {}
    for value in values:
        for token in value.split(","):
            if token.strip():
                tokens.setdefault(token.strip().lower(), token.strip())
    rest = [(k, v) for k, v in headers if k.lower() != b"vary"]
    return [*rest, (b"vary", ", ".join(tokens.values()).encode("latin-1"))]


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = scope["path"].startswith(_DOCS_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                present = {key.lower() for key, _ in headers}
                for name, value in SECURITY_HEADERS.items():
                    if is_docs and name in {"Content-Security-Policy", "Cache-Control"}:
                        continue
                    if name.lower().encode() in present:  # e.g. Cache-Control set by HttpCacheMiddleware
                        continue
                    headers.append((name.lower().encode(), value.encode()))
                message["headers"] = _merge_vary(headers)
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Rejects bodies above `max_bytes` by declared length and by bytes actually received."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > self.max_bytes):
            await self._reject(send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLargeError:
            await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        body = (
            b'{"error":{"code":"payload_too_large",'
            b'"message":"El cuerpo de la solicitud es demasiado grande."}}'
        )
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class _BodyTooLargeError(Exception):
    pass


def client_key(host: str | None) -> str:
    """Canonical limiter key for a client address.

    IPv4-mapped IPv6 (`::ffff:203.0.113.9`) becomes its IPv4 form and other IPv6 addresses their compressed
    form, so one client cannot hold several buckets by spelling its address differently. Anything that is
    not an IP address (`unknown`, a unix socket) is kept as is.
    """
    if not host:
        return "unknown"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    return str(address)


def request_client_key(request: Request) -> str:
    return client_key(request.client.host if request.client else None)


class SlidingWindowRateLimiter:
    """Per-process, per-client limiter. A multi-instance deployment needs a shared store instead.

    At most `max_keys` clients are tracked. When a new client arrives at the cap, clients whose hits have all
    expired are dropped first; if none are, the least recently active client is evicted and its count
    restarts. That fails towards availability: a flood of addresses cannot grow memory or lock real visitors
    out, and the price is that the limiter can forget the evicted client (a client with many addresses is not
    stopped by this limiter anyway).
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock  # injectable so tests need not sleep
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()  # least recently active first
        self._lock = Lock()
        self._calls = 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._hits)

    def _valid(self, key: str, now: float) -> deque[float] | None:
        """Hits of `key` still inside the window (expired ones dropped); None when it has none."""
        hits = self._hits.get(key)
        if hits is None:
            return None
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if not hits:
            del self._hits[key]
            return None
        return hits

    def is_full(self, key: str) -> bool:
        with self._lock:
            hits = self._valid(key, self._clock())
            return hits is not None and len(hits) >= self.limit

    def retry_after(self, key: str) -> int:
        """Whole seconds (at least 1) until `key` is below the limit again."""
        now = self._clock()
        with self._lock:
            hits = self._valid(key, now)
            if hits is None or len(hits) < self.limit:
                return 1
            # The hit whose expiry brings the count to limit - 1.
            return max(1, math.ceil(self.window - (now - hits[len(hits) - self.limit])))

    def _sweep(self, now: float) -> None:
        for stale in [k for k, h in self._hits.items() if not h or now - h[-1] > self.window]:
            del self._hits[stale]

    def allow(self, key: str) -> bool:
        """Record a hit and return True, or return False (recording nothing) when `key` is at the limit."""
        now = self._clock()
        with self._lock:
            self._calls += 1
            if self._calls % 1024 == 0:  # drop keys whose hits all expired, so idle clients do not accumulate
                self._sweep(now)
            hits = self._valid(key, now)
            if hits is not None and len(hits) >= self.limit:
                return False
            if hits is None:
                if len(self._hits) >= self.max_keys:
                    self._sweep(now)
                    while len(self._hits) >= self.max_keys:
                        self._hits.popitem(last=False)
                hits = self._hits[key] = deque()
            hits.append(now)
            self._hits.move_to_end(key)
            return True


DOSSIER_LIMIT = 30
DOSSIER_WINDOW_SECONDS = 60.0
dossier_rate_limiter = SlidingWindowRateLimiter(DOSSIER_LIMIT, DOSSIER_WINDOW_SECONDS)


def limit_dossier_builds(request: Request) -> None:
    """Per-process, per-IP limit on GET dossier (each uncached build is expensive)."""
    client = request_client_key(request)
    if not dossier_rate_limiter.allow(client):
        raise HTTPException(status_code=429, detail="Demasiados expedientes solicitados. Intente más tarde.")


REVIEW_LIMIT = 30
REVIEW_WINDOW_SECONDS = 60.0
review_rate_limiter = SlidingWindowRateLimiter(REVIEW_LIMIT, REVIEW_WINDOW_SECONDS)


def limit_review_writes(request: Request) -> None:
    client = request_client_key(request)
    if not review_rate_limiter.allow(client):
        raise HTTPException(status_code=429, detail="Demasiadas revisiones recientes. Intente más tarde.")


READ_PREFIX = "/api/v1/"
READ_EXEMPT_PATHS = frozenset({"/api/v1/health"})


class ReadRateLimitMiddleware:
    """Per-client limit on anonymous GET routes: a general one and a stricter one for requests carrying `q`.

    In memory, per worker process, reset on restart. The client is `scope["client"]`, which uvicorn rewrites
    from `X-Forwarded-For` only when the TCP peer is in `FORWARDED_ALLOW_IPS` (in production: Caddy and the
    web container, which forwards the visitor's address on its server-side calls). Addresses in `exempt` are
    never counted (empty in production); the check uses that resolved address, not a header.
    A request is counted before the HTTP cache runs, so a conditional request answered with 304 counts too.
    A request that is rejected consumes no budget in either limiter. A limit of 0 switches that limit off.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        per_minute: int,
        search_per_minute: int,
        exempt: list[str] | tuple[str, ...] = (),
        window_seconds: float = 60.0,
        max_keys: int = 5_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.general = (
            SlidingWindowRateLimiter(per_minute, window_seconds, max_keys, clock) if per_minute > 0 else None
        )
        self.search = (
            SlidingWindowRateLimiter(search_per_minute, window_seconds, max_keys, clock)
            if search_per_minute > 0
            else None
        )
        self.exempt = parse_exempt_networks(tuple(exempt))

    def _is_exempt(self, client: str) -> bool:
        try:
            address = ipaddress.ip_address(client)
        except ValueError:
            return False
        return any(address in network for network in self.exempt if network.version == address.version)

    @staticmethod
    def is_search(raw: bytes) -> bool:
        """True when the query string carries a `q` the API will run as a search.

        Parsed like the API parses it (Starlette's `QueryParams`: the last `q` wins) and trimmed like the API
        trims it (`trim_query_text`), so a `q` that is blank after trimming, such as `%20` or `%C2%A0`, is
        not a search here and is a 422 there.
        """
        text = QueryParams(raw).get("q")
        return text is not None and bool(trim_query_text(text))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or scope["method"] not in {"GET", "HEAD"}
            or not path.startswith(READ_PREFIX)
            or path in READ_EXEMPT_PATHS
            or (self.general is None and self.search is None)
        ):
            await self.app(scope, receive, send)
            return
        client_info = scope.get("client")
        client = client_key(client_info[0] if client_info else None)
        if self._is_exempt(client):
            await self.app(scope, receive, send)
            return
        retry_after = self._check(client, search=self.is_search(scope.get("query_string", b"")))
        if retry_after is None:
            await self.app(scope, receive, send)
            return
        body = (
            b'{"error":{"code":"rate_limited",'
            b'"message":"Demasiadas solicitudes recientes. Intente m\xc3\xa1s tarde."}}'
        )
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"retry-after", str(retry_after).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    def _check(self, client: str, *, search: bool) -> int | None:
        """None when allowed (a hit is recorded in each limiter that applies), otherwise the whole seconds to
        wait. Nothing is recorded in any limiter when the request is rejected. There is no `await` between the
        check and the record, so the pair is atomic for the worker's event loop."""
        applicable = [
            limiter for limiter in (self.general, self.search if search else None) if limiter is not None
        ]
        waits = [limiter.retry_after(client) for limiter in applicable if limiter.is_full(client)]
        if waits:
            return max(waits)  # every full limiter must have room again
        for limiter in applicable:
            limiter.allow(client)
        return None
