"""Per-run trace records (JSONL) and the summary printed by ``veedor dossier traces``."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Trace(BaseModel):
    ocid: str
    started_at: datetime
    total_ms: float
    node_timings_ms: dict[str, float] = Field(default_factory=dict)
    llm_attempts: int = 0
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    estimated_cost_usd: float | None = None
    grounding_passed: bool | None = None
    grounding_n_checked: int | None = None
    attempt_log: list[dict[str, Any]] = Field(default_factory=list)
    final_mode: str
    fallback_reason: str | None = None
    error: str | None = None


class TraceWriter:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "investigator.jsonl"

    def write(self, trace: Trace) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(trace.model_dump_json() + "\n")

    def read(self) -> list[Trace]:
        if not self.path.is_file():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [Trace.model_validate_json(line) for line in lines if line.strip()]


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def summarise(traces: list[Trace]) -> dict[str, Any]:
    llm_runs = [t for t in traces if t.llm_attempts > 0]
    first_pass = [t for t in llm_runs if t.attempt_log and t.attempt_log[0].get("passed")]
    retried_ok = [t for t in llm_runs if t.final_mode == "llm" and t not in first_pass]
    latencies = [t.total_ms for t in traces]
    costs = [t.estimated_cost_usd for t in traces if t.estimated_cost_usd is not None]
    return {
        "runs": len(traces),
        "by_final_mode": {
            m: sum(t.final_mode == m for t in traces) for m in sorted({t.final_mode for t in traces})
        },
        "errors": sum(t.error is not None for t in traces),
        "llm_runs": len(llm_runs),
        "llm_passed_first_attempt": len(first_pass),
        "llm_passed_after_retry": len(retried_ok),
        "llm_fell_back_to_template": sum(t.fallback_reason is not None for t in llm_runs),
        "llm_grounding_pass_rate": (len(first_pass) + len(retried_ok)) / len(llm_runs) if llm_runs else None,
        "latency_ms_p50": _percentile(latencies, 0.5),
        "latency_ms_p95": _percentile(latencies, 0.95),
        "prompt_tokens": sum(t.prompt_tokens or 0 for t in traces),
        "completion_tokens": sum(t.completion_tokens or 0 for t in traces),
        "estimated_cost_usd": sum(costs) if costs else None,
    }


def trace_to_json(trace: Trace) -> str:
    return json.dumps(trace.model_dump(mode="json"), ensure_ascii=False)
