"""The single door through which every tool call passes: allow-list, budget, validation, log, telemetry."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from veedor.agents.investigation import obs
from veedor.domain.investigation.models import ToolCall
from veedor.domain.investigation.policies import ALLOWED_TOOLS, MAX_TOOL_CALLS_PER_SPECIALIST
from veedor.infrastructure.mcp.port import RawResult, ToolBackend

T = TypeVar("T", bound=BaseModel)


@dataclass
class ToolOutput[V]:
    call: ToolCall
    value: V | None = None  # the validated model; None on any failure, skip or not-found

    @property
    def not_found(self) -> bool:
        return self.call.outcome == "ok" and self.call.reason == "not_found"


class RunBudget:
    """At most `MAX_TOOL_CALLS_PER_SPECIALIST` executed calls per specialist dispatch."""

    def __init__(self, limit: int = MAX_TOOL_CALLS_PER_SPECIALIST) -> None:
        self.limit = limit
        self.used = 0

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit


class ToolRunner:
    def __init__(self, backend: ToolBackend, log: list[ToolCall], ocid: str) -> None:
        self._backend = backend
        self._log = log
        self._ocid = ocid

    def skip(self, specialist: str, tool: str, target: str, reason: str) -> ToolOutput[Any]:
        now = datetime.now(UTC)
        call = ToolCall(
            specialist=specialist,
            tool=tool,
            target=target,
            started_at=now,
            ended_at=now,
            duration_ms=0.0,
            outcome="skipped",
            attempts=0,
            reason=reason,
        )
        self._log.append(call)
        return ToolOutput(call)

    def run(
        self,
        *,
        specialist: str,
        tool: str,
        target: str,
        arguments: dict[str, Any],
        model: type[T],
        budget: RunBudget,
        expect_ruc: str | None = None,
        timeout_s: float | None = None,
    ) -> ToolOutput[T]:
        """Call one tool. Unknown tools and exhausted budgets are logged as skipped, never executed."""
        if tool not in ALLOWED_TOOLS.get(specialist, frozenset()):  # type: ignore[call-overload]
            return self.skip(specialist, tool, target, "tool_not_allowed")
        if budget.exhausted:
            return self.skip(specialist, tool, target, "budget_exhausted")
        budget.used += 1
        started_at, clock = datetime.now(UTC), time.perf_counter()
        with obs.span("tool", ocid=self._ocid, specialist=specialist, tool=tool):
            raw: RawResult = self._backend.call(tool, arguments, timeout_s)
            outcome, reason, value = self._interpret(raw, model, expect_ruc)
        duration = round((time.perf_counter() - clock) * 1000, 2)
        obs.record_tool_call(tool, outcome, duration)
        call = ToolCall(
            specialist=specialist,
            tool=tool,
            target=target,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            duration_ms=duration,
            outcome=outcome,
            attempts=raw.attempts,
            reason=reason,
        )
        self._log.append(call)
        return ToolOutput(call, value)

    @staticmethod
    def _interpret(
        raw: RawResult, model: type[T], expect_ruc: str | None
    ) -> tuple[str, str | None, T | None]:
        if raw.status != "ok":
            return raw.status, raw.reason, None
        if raw.data is None:
            return "ok", raw.reason, None  # the source answered that it has no record
        try:
            value = model.model_validate(raw.data)
        except (ValidationError, ValueError, RecursionError):
            return "invalid_result", "schema_mismatch", None  # the error text may echo data: dropped
        if expect_ruc is not None and getattr(value, "ruc", expect_ruc) != expect_ruc:
            return "invalid_result", "identifier_mismatch", None
        return "ok", raw.reason, value
