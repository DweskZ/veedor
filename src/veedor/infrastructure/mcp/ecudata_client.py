"""Read-only client for the EcuDataMCP server over stdio, one long-lived session per batch.

The server is launched once (``uvx ecuador-mcp --transport stdio``) and kept for the whole batch, so
the large Superintendencia de Compañías directory is loaded once. The session runs on a private event
loop in a background thread; `call` is synchronous, has a hard timeout, retries a failed or timed-out
call at most once, and returns a structured `RawResult` instead of raising.

Verified against the running server (v0.15.0): with ``format="json"`` the result is in
``structured_content``; a tool error arrives as ``is_error`` with a text message; the SRI tool fails with
HTTP 500 from the SRI's own establishments page unless ``include_establecimientos`` is false.
The text of an error is only used to pick a closed reason code and is never kept.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

from veedor.infrastructure.mcp.port import RawResult, ToolBackend

DEFAULT_COMMAND = ("uvx", "ecuador-mcp", "--transport", "stdio")
START_TIMEOUT_S = 180.0
DEFAULT_CALL_TIMEOUT_S = 60.0
TOOL_TIMEOUT_S: dict[str, float] = {
    "get_compania_info": 90.0,  # the first call loads a ~230k-row directory (about 25 s measured)
    "get_financials": 60.0,
    "get_sri_ruc_info": 30.0,
    "list_catalogo": 60.0,
    "get_contraloria_informe": 60.0,
}
MAX_PAYLOAD_BYTES = 2_000_000
MAX_ATTEMPTS = 2  # one call and at most one retry


class EcuDataMcpSession:
    """Context manager owning the stdio session. Use as ``with EcuDataMcpSession() as backend:``."""

    def __init__(
        self,
        command: tuple[str, ...] = DEFAULT_COMMAND,
        *,
        start_timeout_s: float = START_TIMEOUT_S,
        tool_timeouts: dict[str, float] | None = None,
    ) -> None:
        self._command = command
        self._start_timeout = start_timeout_s
        self._timeouts = {**TOOL_TIMEOUT_S, **(tool_timeouts or {})}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stop: asyncio.Event | None = None
        self._session: Any = None
        self._tools: frozenset[str] = frozenset()
        self.start_failed = False

    # lifecycle -------------------------------------------------------------------------------
    def __enter__(self) -> EcuDataMcpSession:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="ecudata-mcp", daemon=True)
        self._thread.start()
        if not self._ready.wait(self._start_timeout) or self._session is None:
            self.start_failed = True

    def close(self) -> None:
        loop, stop = self._loop, self._stop
        if loop is not None and stop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(stop.set)
        if self._thread is not None:
            self._thread.join(timeout=15)

    @property
    def available(self) -> bool:
        return self._session is not None and not self.start_failed

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            loop.run_until_complete(self._main())
        except Exception:  # noqa: BLE001 - a failed launch is reported as an unavailable server
            self.start_failed = True
        finally:
            self._session = None
            self._ready.set()
            loop.close()

    async def _main(self) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        self._stop = asyncio.Event()
        params = StdioServerParameters(command=self._command[0], args=list(self._command[1:]))
        with open(os.devnull, "w") as errlog:  # server logs are never kept
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), self._start_timeout)
                    listing = await asyncio.wait_for(session.list_tools(), 60)
                    self._tools = frozenset(t.name for t in listing.tools)
                    self._session = session
                    self._ready.set()
                    await self._stop.wait()

    # calls -----------------------------------------------------------------------------------
    def call(self, tool: str, arguments: dict[str, Any], timeout_s: float | None = None) -> RawResult:
        if not self.available or self._loop is None:
            return RawResult("upstream_error", attempts=0, reason="server_unavailable")
        if tool not in self._tools:
            return RawResult("upstream_error", attempts=0, reason="server_unavailable")
        timeout = timeout_s or self._timeouts.get(tool, DEFAULT_CALL_TIMEOUT_S)
        future = asyncio.run_coroutine_threadsafe(self._call(tool, arguments, timeout), self._loop)
        try:
            return future.result(timeout * MAX_ATTEMPTS + 10)
        except (FutureTimeout, TimeoutError):
            future.cancel()
            return RawResult("timeout", attempts=MAX_ATTEMPTS)
        except Exception:  # noqa: BLE001 - the contract of `call` is to never raise
            return RawResult("upstream_error", attempts=1, reason="server_unavailable")

    async def _call(self, tool: str, arguments: dict[str, Any], timeout: float) -> RawResult:
        result = RawResult("upstream_error", attempts=0)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            result = await self._once(tool, arguments, timeout, attempt)
            if result.status in ("ok", "invalid_result") or result.reason in (
                "not_found",
                "server_unavailable",
            ):
                return result
        return result

    async def _once(self, tool: str, arguments: dict[str, Any], timeout: float, attempt: int) -> RawResult:
        try:
            response = await asyncio.wait_for(self._session.call_tool(tool, arguments), timeout)
        except TimeoutError:
            return RawResult("timeout", attempts=attempt)
        except Exception:  # noqa: BLE001 - transport failure (closed pipe, protocol error)
            return RawResult("upstream_error", attempts=attempt, reason="server_unavailable")
        return parse_response(response, attempt)


def parse_response(response: Any, attempt: int = 1) -> RawResult:
    """Classify a `CallToolResult` (pure; the text of an error is read only to choose a reason)."""
    texts = [c.text for c in (response.content or []) if getattr(c, "text", None) is not None]
    if response.is_error:
        message = " ".join(texts).casefold()
        if "no se encontr" in message:
            return RawResult("ok", None, attempt, reason="not_found")
        if "server error" in message or "httpstatuserror" in message or "http" in message:
            return RawResult("upstream_error", None, attempt, reason="upstream_http_error")
        return RawResult("upstream_error", None, attempt, reason="tool_reported_error")
    data = response.structured_content
    if data is None and texts:
        text = texts[0]
        if len(text) > MAX_PAYLOAD_BYTES:
            return RawResult("invalid_result", None, attempt, reason="oversized_content")
        try:
            data = json.loads(text)
        except (ValueError, RecursionError):
            return RawResult("invalid_result", None, attempt, reason="malformed_content")
    if data is None:
        return RawResult("invalid_result", None, attempt, reason="malformed_content")
    if len(json.dumps(data, default=str)) > MAX_PAYLOAD_BYTES:
        return RawResult("invalid_result", None, attempt, reason="oversized_content")
    return RawResult("ok", data, attempt)


class UnavailableBackend:
    """Used when live lookups are off or the server could not start: every call is a recorded failure."""

    def call(self, tool: str, arguments: dict[str, Any], timeout_s: float | None = None) -> RawResult:
        return RawResult("upstream_error", attempts=0, reason="server_unavailable")


def build_backend() -> ToolBackend:
    """Backend of unavailable lookups; the CLI replaces it with an `EcuDataMcpSession`."""
    return UnavailableBackend()
