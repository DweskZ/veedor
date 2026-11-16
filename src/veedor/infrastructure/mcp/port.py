"""Port of every read-only tool the investigation may call (MCP or local), with structured outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

Status = Literal["ok", "timeout", "upstream_error", "invalid_result", "skipped"]


@dataclass(frozen=True)
class RawResult:
    """What a backend returns for one call. `data` is untrusted until a pydantic model accepts it.

    `reason` is a member of the closed vocabulary `domain.investigation.vocab.Reason`; it never
    carries text from the tool.
    """

    status: Status
    data: Any | None = None
    attempts: int = 1
    reason: str | None = None


class ToolBackend(Protocol):
    def call(self, tool: str, arguments: dict[str, Any], timeout_s: float | None = None) -> RawResult:
        """Run one allow-listed tool. Must never raise: failures are returned as a `RawResult`."""
        ...
