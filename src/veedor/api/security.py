"""Hardening: security headers, request size limit and a small in-memory rate limiter."""

from __future__ import annotations

import ipaddress
import math
import time
from collections import defaultdict, deque
from threading import Lock
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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


class SlidingWindowRateLimiter:
    """Per-process, per-client limiter. A multi-instance deployment needs a shared store instead."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._calls = 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def is_full(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return False
            return sum(1 for h in hits if now - h <= self.window) >= self.limit

    def retry_after(self, key: str) -> int:
        """Whole seconds (at least 1) until the oldest hit of `key` leaves the window."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 1
            return max(1, math.ceil(self.window - (now - hits[0])))

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._calls += 1
            if self._calls % 1024 == 0:  # drop keys whose hits all expired, so idle clients do not accumulate
                for stale in [k for k, h in self._hits.items() if not h or now - h[-1] > self.window]:
                    del self._hits[stale]
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


DOSSIER_LIMIT = 30
DOSSIER_WINDOW_SECONDS = 60.0
dossier_rate_limiter = SlidingWindowRateLimiter(DOSSIER_LIMIT, DOSSIER_WINDOW_SECONDS)


def limit_dossier_builds(request: Request) -> None:
    """Per-process, per-IP limit on GET dossier (each uncached build is expensive)."""
    client = request.client.host if request.client else "unknown"
    if not dossier_rate_limiter.allow(client):
        raise HTTPException(status_code=429, detail="Demasiados expedientes solicitados. Intente más tarde.")


REVIEW_LIMIT = 30
REVIEW_WINDOW_SECONDS = 60.0
review_rate_limiter = SlidingWindowRateLimiter(REVIEW_LIMIT, REVIEW_WINDOW_SECONDS)


def limit_review_writes(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    if not review_rate_limiter.allow(client):
        raise HTTPException(status_code=429, detail="Demasiadas revisiones recientes. Intente más tarde.")


READ_PREFIX = "/api/v1/"
READ_EXEMPT_PATHS = frozenset({"/api/v1/health"})


class ReadRateLimitMiddleware:
    """Per-client limit on anonymous GET routes: a general one and a stricter one for requests carrying `q`.

    In memory, per worker process, reset on restart. The client is `scope["client"]`, which uvicorn rewrites
    from `X-Forwarded-For` only when the TCP peer is in `FORWARDED_ALLOW_IPS`. Addresses in `exempt` (the web
    container's server-side calls) are never counted; the check uses that resolved address, not a header.
    A request is counted before the HTTP cache runs, so a conditional request answered with 304 counts too.
    A limit of 0 switches that limit off.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        per_minute: int,
        search_per_minute: int,
        exempt: list[str] | tuple[str, ...] = (),
        window_seconds: float = 60.0,
    ) -> None:
        self.app = app
        self.general = SlidingWindowRateLimiter(per_minute, window_seconds) if per_minute > 0 else None
        self.search = (
            SlidingWindowRateLimiter(search_per_minute, window_seconds) if search_per_minute > 0 else None
        )
        self.exempt = tuple(ipaddress.ip_network(value, strict=False) for value in exempt)

    def _is_exempt(self, client: str) -> bool:
        try:
            address = ipaddress.ip_address(client)
        except ValueError:
            return False
        return any(address in network for network in self.exempt if network.version == address.version)

    @staticmethod
    def _has_query_text(raw: bytes) -> bool:
        pairs = parse_qsl(raw.decode("latin-1"), keep_blank_values=True)
        return any(key == "q" and value.strip() for key, value in pairs)

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
        client = client_info[0] if client_info else "unknown"
        if self._is_exempt(client):
            await self.app(scope, receive, send)
            return
        retry_after = self._check(client, search=self._has_query_text(scope.get("query_string", b"")))
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
        """None when allowed, otherwise the whole seconds to wait."""
        if self.general is not None and not self.general.allow(client):
            return self.general.retry_after(client)
        if search and self.search is not None and not self.search.allow(client):
            return self.search.retry_after(client)
        return None
