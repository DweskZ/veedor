"""Hardening: security headers, request size limit and a small in-memory rate limiter."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

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
                for name, value in SECURITY_HEADERS.items():
                    if is_docs and name in {"Content-Security-Policy", "Cache-Control"}:
                        continue
                    headers.append((name.lower().encode(), value.encode()))
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

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
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
