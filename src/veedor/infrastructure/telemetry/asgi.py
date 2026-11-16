"""ASGI middleware: one server span and RED metrics per request, keyed by route TEMPLATE.

Written in place of the stock FastAPI instrumentor because that one records the raw URL
(`url.path`, `http.target`), which would put process ids and RUCs into span attributes. Here the
span name and the `http.route` label are the route template (`/api/v1/processes/{ocid}`), and
only allow-listed attributes are ever set. Health checks are not traced.
"""

from __future__ import annotations

import time
from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from veedor.infrastructure.telemetry import runtime

HEALTH_PATH_SUFFIX = "/health"
UNMATCHED_ROUTE = "unmatched"
_KNOWN_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


def route_template(scope: Scope) -> str:
    """Full route template, e.g. `/api/v1/processes/{ocid}`; `unmatched` when no route matched.

    Starlette keeps only the inner router's path in `scope["route"]` (the include prefix is
    lost), so the prefix is recovered from the real path: the part left of the rendered route.
    """
    route = getattr(scope.get("route"), "path_format", None)
    if not route:
        return UNMATCHED_ROUTE
    rendered = route
    for key, value in scope.get("path_params", {}).items():
        rendered = rendered.replace("{" + key + "}", str(value))
    path = scope["path"]
    prefix = path[: len(path) - len(rendered)] if rendered and path.endswith(rendered) else ""
    return f"{prefix}{route}"


class TelemetryMiddleware:
    def __init__(self, app: ASGIApp, excluded_suffixes: Iterable[str] = (HEALTH_PATH_SUFFIX,)) -> None:
        self.app = app
        self.excluded = tuple(excluded_suffixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not runtime.is_enabled() or scope["path"].endswith(self.excluded):
            await self.app(scope, receive, send)
            return
        method = scope["method"] if scope["method"] in _KNOWN_METHODS else "_OTHER"
        status = 500  # replaced by the real response status when one is sent

        async def send_capturing_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        started = time.perf_counter()
        with runtime.server_span(f"{method} {UNMATCHED_ROUTE}", **{"http.request.method": method}) as handle:
            try:
                await self.app(scope, receive, send_capturing_status)
            finally:
                route = route_template(scope)
                handle.update_name(f"{method} {route}")
                handle.set_attributes(
                    **{"http.route": route, "http.response.status_code": status},
                    ocid=scope.get("path_params", {}).get("ocid"),
                )
                if status >= 500:
                    handle.mark_error()
                runtime.record_http_request(method, route, status, time.perf_counter() - started)


def instrument_app(app: ASGIApp) -> None:
    """Add the middleware to a FastAPI/Starlette app (outermost user middleware)."""
    app.add_middleware(TelemetryMiddleware)  # type: ignore[attr-defined]
