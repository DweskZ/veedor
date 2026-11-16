"""Telemetry bridge: the real functions when `veedor.infrastructure.telemetry` exists, no-ops otherwise.

Only enumerated values (ocid, specialist, tool, outcome, counts, durations, model name, token counts)
are ever passed to a span or a metric. Nothing from a tool result or a prompt goes through here.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from typing import Any

try:
    from veedor.infrastructure import telemetry as _telemetry
except Exception:  # noqa: BLE001 - telemetry is optional; the agents must run without it
    _telemetry = None


def span(name: str, **attributes: Any) -> AbstractContextManager[Any]:
    if _telemetry is None:
        return nullcontext()
    return _telemetry.span(name, **attributes)


def _call(name: str, *args: Any, **kwargs: Any) -> None:
    function = getattr(_telemetry, name, None) if _telemetry is not None else None
    if function is None:
        return
    try:
        function(*args, **kwargs)
    except Exception:  # noqa: BLE001 - observability never breaks an investigation
        return


def record_llm_usage(model: str, prompt_tokens: int, completion_tokens: int) -> None:
    _call("record_llm_usage", model, prompt_tokens, completion_tokens)


def record_tool_call(tool: str, outcome: str, duration_ms: float) -> None:
    _call("record_tool_call", tool, outcome, duration_ms)


def record_grounding(passed: bool, mode: str) -> None:
    _call("record_grounding", passed, mode)


def record_specialist_run(specialist: str, outcome: str = "ok") -> None:
    _call("record_specialist_run", specialist, outcome)


def record_investigation(final_mode: str, duration_ms: float | None = None) -> None:
    _call("record_investigation", final_mode, duration_ms)
