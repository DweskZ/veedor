"""Run the investigator graph for one ocid and write its trace record."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veedor.agents.investigation import obs
from veedor.agents.investigation.supervisor import InvestigationPorts
from veedor.agents.investigator.graph import RECURSION_LIMIT, build_graph
from veedor.agents.investigator.nodes.load_evidence import EvidenceLoader
from veedor.agents.investigator.tracing import Trace, TraceWriter
from veedor.domain.dossier.models import Dossier
from veedor.infrastructure.llm.port import ChatModelPort
from veedor.infrastructure.llm.pricing import estimate_cost_usd


class InvestigatorAgent:
    def __init__(
        self,
        *,
        loader: EvidenceLoader,
        chat_model: ChatModelPort | None = None,
        trace_dir: Path | None = None,
        config_dir: Path | None = None,
        investigation: InvestigationPorts | None = None,
    ) -> None:
        self._graph = build_graph(loader=loader, chat_model=chat_model, investigation=investigation)
        self._chat_model = chat_model
        self._traces = TraceWriter(trace_dir) if trace_dir else None
        self._config_dir = config_dir

    def run(self, ocid: str) -> Dossier:
        return self.run_state(ocid)["dossier"]

    def run_state(self, ocid: str) -> dict[str, Any]:
        """Run the graph and return its final state (the dossier is `state["dossier"]`)."""
        started_at, clock = datetime.now(UTC), time.perf_counter()
        try:
            state = self._graph.invoke({"ocid": ocid}, config={"recursion_limit": RECURSION_LIMIT})
        except Exception as exc:
            self._trace(
                Trace(
                    ocid=ocid,
                    started_at=started_at,
                    total_ms=_ms(clock),
                    final_mode="error",
                    error=type(exc).__name__,
                )
            )
            raise
        dossier: Dossier = state["dossier"]
        obs.record_investigation(dossier.mode, _ms(clock))
        prompt, completion = state.get("prompt_tokens"), state.get("completion_tokens")
        model = state.get("model")
        cost = estimate_cost_usd(model, prompt, completion, self._config_dir) if self._config_dir else None
        self._trace(
            Trace(
                ocid=ocid,
                started_at=started_at,
                total_ms=_ms(clock),
                node_timings_ms=state.get("timings_ms", {}),
                llm_attempts=state.get("attempts", 0),
                model=model,
                prompt_tokens=prompt if state.get("llm_used") else None,
                completion_tokens=completion if state.get("llm_used") else None,
                estimated_cost_usd=cost,
                grounding_passed=dossier.grounding_report.passed,
                grounding_n_checked=dossier.grounding_report.n_checked,
                attempt_log=state.get("attempt_log", []),
                final_mode=dossier.mode,
                fallback_reason=dossier.fallback_reason,
            )
        )
        return state

    def _trace(self, trace: Trace) -> None:
        if self._traces is not None:
            self._traces.write(trace)


def _ms(clock: float) -> float:
    return round((time.perf_counter() - clock) * 1000, 2)
