"""Backend that routes allow-listed tools: MCP tools to the session, local tools to in-process functions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from veedor.domain.investigation.vocab import MCP_TOOLS
from veedor.infrastructure.investigations.lake_tools import LakeTools
from veedor.infrastructure.mcp.port import RawResult, ToolBackend

LocalTool = Callable[[dict[str, Any]], Any]


def similar_summary(lake: LakeTools, arguments: dict[str, Any]) -> dict[str, Any]:
    """Same-buyer neighbours (vector index) above a similarity floor that fall near the reference date.

    `basis` is ``description`` only when the query and every counted neighbour were embedded from the
    CPC text plus a description; otherwise ``classification`` (the object's CPC class only).
    """
    from veedor.use_cases.similar_processes import find_similar

    ocid, window = arguments["ocid"], int(arguments["window_days"])
    floor = float(arguments["similarity_floor"])
    reference = date.fromisoformat(arguments["reference_day"])
    neighbours = [n for n in find_similar(ocid, k=int(arguments["k"]), same_buyer=True) if n.ocid != ocid]
    above = [n for n in neighbours if n.similarity >= floor]
    days = lake.reference_days([n.ocid for n in above])
    near = [
        n
        for n in above
        if n.ocid in days and abs((date.fromisoformat(days[n.ocid]) - reference).days) <= window
    ]
    basis = lake.embedding_basis([ocid, *[n.ocid for n in near]])
    kind = (
        "description"
        if basis and all(basis.get(o) == "description" for o in (ocid, *[n.ocid for n in near]))
        else "classification"
    )
    amounts = [n.award_total for n in near if n.award_total is not None]
    return {
        "neighbours_examined": len(neighbours),
        "n_above_floor": len(above),
        "basis": kind,
        "n_in_window": len(near),
        "n_with_amount": len(amounts),
        "combined_amount": round(float(sum(amounts)), 2) if amounts else None,
    }


class CompositeBackend:
    def __init__(self, mcp: ToolBackend, local: dict[str, LocalTool]) -> None:
        self._mcp = mcp
        self._local = local

    def call(self, tool: str, arguments: dict[str, Any], timeout_s: float | None = None) -> RawResult:
        if tool in MCP_TOOLS:
            return self._mcp.call(tool, arguments, timeout_s)
        function = self._local.get(tool)
        if function is None:
            return RawResult("skipped", attempts=0, reason="tool_not_allowed")
        return self._run_local(function, arguments)

    @staticmethod
    def _run_local(function: LocalTool, arguments: dict[str, Any]) -> RawResult:
        try:
            return RawResult("ok", function(arguments))
        except ImportError:
            return RawResult("skipped", attempts=0, reason="vectors_unavailable")
        except Exception as exc:  # noqa: BLE001 - classified by type name; the message is never kept
            return _classify_local(exc)


def _classify_local(exc: Exception) -> RawResult:
    name = type(exc).__name__
    if name == "VectorsUnavailable":
        return RawResult("upstream_error", reason="vectors_unavailable")
    if name == "ProcessNotIndexed":
        return RawResult("skipped", attempts=0, reason="not_indexed")
    if isinstance(exc, FileNotFoundError) or name.endswith("IOException") or "duckdb" in type(exc).__module__:
        return RawResult("upstream_error", reason="lake_unavailable")
    if isinstance(exc, ValueError | KeyError):
        return RawResult("skipped", attempts=0, reason="no_identifier")
    return RawResult("upstream_error", reason="tool_reported_error")


def build_backend(mcp: ToolBackend, lake: LakeTools) -> CompositeBackend:
    return CompositeBackend(
        mcp,
        {"pair_awards": lake.pair_awards, "similar_processes": lambda args: similar_summary(lake, args)},
    )
