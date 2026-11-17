"""HTTP caching: one table of route classes, validators (ETag) and conditional requests.

Everything is decided here, in one place. A route not listed in `RULES` is not cacheable and keeps
`Cache-Control: no-store` from `SecurityHeadersMiddleware`; the same goes for every non-GET request,
every response that is not a 200, and every request carrying `Authorization`.

ETag. Weak (`W/"..."`), because a proxy may re-encode the body (Caddy `encode`). Two modes:

* ``signature``: a hash of the API version, the data build signature (`lake.data_version()`: path,
  modification time and size of every parquet table and of `build_summary.json`), the path and the
  normalised query. The same on every worker, it changes exactly when the data or the code version
  changes, and a matching `If-None-Match` is answered with 304 *before* the route runs: no query, no
  serialisation. A route whose body also depends on state outside the lake adds a fingerprint of it.
* ``body``: a hash of the response body, for routes whose content depends on state that is not part of
  the data build (the vector index, stored investigations, the dossier cache). The route runs, only
  the transfer is saved.

The middleware never stores a body, so a cached or 304 path cannot serve anything the route did not
just produce through its response model (masking of natural persons happens there). A 304 has no body.

Vary. `Vary: Origin` is always sent on a cacheable response, including 304: the CORS middleware adds
`Access-Control-Allow-Origin` according to the request origin, and a shared cache must not replay one
origin's copy to another.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qsl, urlencode

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from veedor.api.meta import VERSION

API_PREFIX = "/api/v1"

AGGREGATE = "public, max-age=300, stale-while-revalidate=86400"
PER_PROCESS = "public, max-age=60"
LISTING = "public, max-age=30"

Mode = Literal["signature", "body"]


@dataclass(frozen=True, slots=True)
class CacheRule:
    cache_control: str
    mode: Mode = "signature"
    extra: Callable[[Scope], str] | None = None  # fingerprint of state outside the data build


def _glossary_fingerprint(scope: Scope) -> str:
    from veedor.api.deps import get_glossary_store

    app = scope.get("app")
    overrides = getattr(app, "dependency_overrides", {}) or {}
    return overrides.get(get_glossary_store, get_glossary_store)().fingerprint()


_SEGMENT = r"[^/]+"
# First match wins. `None` = explicitly never cached.
RULES: tuple[tuple[re.Pattern[str], CacheRule | None], ...] = tuple(
    (re.compile(pattern), rule)
    for pattern, rule in (
        # Never cached: random pick (the point is that it changes), live flags and health.
        (r"/processes/random", None),
        (r"/health", None),
        (r"/meta", None),
        # Data-build aggregates and reference data.
        (r"/stats(?:/by-region|/by-year|/thresholds)?", CacheRule(AGGREGATE)),
        (r"/signals", CacheRule(AGGREGATE)),
        (r"/glossary", CacheRule(AGGREGATE, extra=_glossary_fingerprint)),
        # Lists and searches.
        (r"/processes", CacheRule(LISTING)),
        (r"/buyers/search", CacheRule(LISTING)),
        # Per-process read models and entity pages.
        (rf"/processes/{_SEGMENT}", CacheRule(PER_PROCESS)),
        (rf"/processes/{_SEGMENT}/(?:context|threshold)", CacheRule(PER_PROCESS)),
        # State outside the data build (stored investigation, vector index, dossier cache): body hash.
        (rf"/processes/{_SEGMENT}/(?:provenance|similar|dossier)", CacheRule(PER_PROCESS, mode="body")),
        (rf"/suppliers/{_SEGMENT}", CacheRule(PER_PROCESS)),
        (rf"/buyers/{_SEGMENT}", CacheRule(PER_PROCESS)),
        # Everything else (quotes, reviews, investigation, ask, ...) is not listed: no-store.
    )
)

_ETAG_ITEM = re.compile(r'\*|(?:W/)?"[^"]*"')


def rule_for(path: str) -> CacheRule | None:
    if not path.startswith(API_PREFIX + "/"):
        return None
    tail = path[len(API_PREFIX) :]
    for pattern, rule in RULES:
        if pattern.fullmatch(tail):
            return rule
    return None


def normalise_query(raw: bytes) -> str:
    """Sorted `key=value` pairs, so equivalent queries share one validator. Blank values are kept: they
    can change the answer (a 422 versus the default)."""
    pairs = parse_qsl(raw.decode("latin-1"), keep_blank_values=True)
    return urlencode(sorted(pairs))


def _weak(tag: str) -> str:
    return tag[2:] if tag.startswith("W/") else tag


def matches(if_none_match: str | None, etag: str, *, wildcard: bool = False) -> bool:
    """Weak comparison of an `If-None-Match` list with `etag`. `*` counts only when `wildcard` is set,
    i.e. when the caller already knows the resource exists (it has a 200 in hand)."""
    if not if_none_match:
        return False
    current = _weak(etag)
    return any(
        (item == "*" and wildcard) or _weak(item) == current for item in _ETAG_ITEM.findall(if_none_match)
    )


def _lake_signature(scope: Scope) -> str:
    from veedor.api.deps import get_reader

    app = scope.get("app")
    overrides = getattr(app, "dependency_overrides", {}) or {}
    return overrides.get(get_reader, get_reader)().data_version()


def signature_etag(scope: Scope, rule: CacheRule) -> str:
    material = "\x1f".join(
        (
            VERSION,
            _lake_signature(scope),
            rule.extra(scope) if rule.extra else "",
            scope["path"],
            normalise_query(scope.get("query_string", b"")),
        )
    )
    return f'W/"{hashlib.sha256(material.encode()).hexdigest()[:24]}"'


def body_etag(body: bytes) -> str:
    return f'W/"b-{hashlib.sha256(body).hexdigest()[:24]}"'


def _set(headers: list[tuple[bytes, bytes]], name: bytes, value: str) -> list[tuple[bytes, bytes]]:
    return [(k, v) for k, v in headers if k.lower() != name] + [(name, value.encode())]


def _validator_headers(
    headers: list[tuple[bytes, bytes]], rule: CacheRule, etag: str
) -> list[tuple[bytes, bytes]]:
    headers = _set(headers, b"etag", etag)
    headers = _set(headers, b"cache-control", rule.cache_control)
    existing = [v.decode() for k, v in headers if k.lower() == b"vary"]
    tokens = [t.strip() for value in existing for t in value.split(",") if t.strip()]
    if "origin" not in (t.lower() for t in tokens):
        tokens.append("Origin")
    return _set(headers, b"vary", ", ".join(tokens))


class HttpCacheMiddleware:
    """Innermost middleware: sits inside CORS (which adds the origin headers to what it emits) and
    inside `SecurityHeadersMiddleware` (which adds the rest and leaves `Cache-Control` alone when set)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET":
            await self.app(scope, receive, send)
            return
        request_headers = {k: v for k, v in scope["headers"] if k in (b"authorization", b"if-none-match")}
        rule = rule_for(scope["path"])
        if rule is None or b"authorization" in request_headers:
            await self.app(scope, receive, send)
            return
        if_none_match = request_headers.get(b"if-none-match", b"").decode("latin-1") or None
        if rule.mode == "signature":
            try:
                etag = signature_etag(scope, rule)
            except Exception:  # noqa: BLE001 - no validator is better than a failed request
                await self.app(scope, receive, send)
                return
            if matches(if_none_match, etag):
                await self._not_modified(send, rule, etag)
                return
            await self.app(scope, receive, self._tag(send, rule, etag))
            return
        await self._body_mode(scope, receive, send, rule, if_none_match)

    @staticmethod
    async def _not_modified(send: Send, rule: CacheRule, etag: str) -> None:
        headers = _validator_headers([], rule, etag)
        await send({"type": "http.response.start", "status": 304, "headers": headers})
        await send({"type": "http.response.body", "body": b""})

    @staticmethod
    def _tag(send: Send, rule: CacheRule, etag: str) -> Send:
        """Add the validator headers to a 200 response (anything else is passed through untouched)."""

        async def tagged(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] == 200:
                message["headers"] = _validator_headers(list(message.get("headers", [])), rule, etag)
            await send(message)

        return tagged

    async def _body_mode(
        self, scope: Scope, receive: Receive, send: Send, rule: CacheRule, if_none_match: str | None
    ) -> None:
        """Buffer a 200 response, tag it with a hash of its body and turn it into a 304 on a match."""
        start: Message | None = None
        chunks: list[bytes] = []
        passthrough = False

        async def collect(message: Message) -> None:
            nonlocal start, passthrough
            if passthrough:
                await send(message)
            elif message["type"] == "http.response.start":
                if message["status"] != 200:
                    passthrough = True
                    await send(message)
                else:
                    start = message
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                body = b"".join(chunks)
                etag = body_etag(body)
                assert start is not None
                if matches(if_none_match, etag, wildcard=True):
                    await self._not_modified(send, rule, etag)
                    return
                start["headers"] = _validator_headers(list(start.get("headers", [])), rule, etag)
                await send(start)
                await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, collect)
