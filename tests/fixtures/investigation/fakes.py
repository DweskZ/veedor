"""Fakes for the investigation tests: a scripted tool backend over the captured fixtures, a fake model."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from veedor.infrastructure.mcp.port import RawResult

DIR = Path(__file__).parent
RUC = "0992764473001"  # placeholder RUC used inside the captured fixtures


def fixture(name: str) -> Any:
    return json.loads((DIR / f"{name}.json").read_text(encoding="utf-8"))


def default_responses() -> dict[str, Any]:
    return {
        "get_compania_info": fixture("get_compania_info"),
        "get_financials": fixture("get_financials"),
        "get_sri_ruc_info": fixture("get_sri_ruc_info"),
        "list_catalogo": fixture("list_catalogo_contraloria"),
        "get_contraloria_informe": fixture("get_contraloria_informe"),
        "pair_awards": {"n_other_awards": 2, "n_with_amount": 2, "total_other_amount": 1500.5},
        "similar_processes": {
            "neighbours_examined": 50, "n_above_floor": 20, "basis": "description",
            "n_in_window": 3, "n_with_amount": 3, "combined_amount": 9000.0,
        },
    }  # fmt: skip


class FakeBackend:
    """Returns the scripted response of a tool: data (ok), a RawResult, or a callable(arguments)."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = {**default_responses(), **(responses or {})}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, tool: str, arguments: dict[str, Any], timeout_s: float | None = None) -> RawResult:
        self.calls.append((tool, arguments))
        response = self.responses.get(tool)
        if callable(response):
            response = response(arguments)
        asked = arguments.get("ruc") or arguments.get("expediente_or_ruc")
        if isinstance(response, RawResult):
            if (
                asked
                and isinstance(response.data, dict)
                and "ruc" in response.data
                and "mismatch" not in str(response.reason)
            ):
                return RawResult(
                    response.status, {**response.data, "ruc": asked}, response.attempts, response.reason
                )
            return response
        if response is None:
            return RawResult("upstream_error", reason="server_unavailable")
        if isinstance(response, dict) and asked and "ruc" in response:
            response = {**response, "ruc": asked}  # the real server echoes the RUC it was asked for
        return RawResult("ok", response)

    @property
    def tools_called(self) -> list[str]:
        return [t for t, _ in self.calls]


class ScriptedModel:
    model_name = "scripted"

    def __init__(self, replies: list[str | Exception]) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str):  # noqa: ANN201
        from veedor.infrastructure.llm.port import LLMResponse

        self.calls.append((system, user))
        reply = self.replies[min(len(self.calls), len(self.replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(text=reply, prompt_tokens=10, completion_tokens=5, model=self.model_name)


TODAY = date(2026, 11, 16)
