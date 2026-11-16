"""LangGraph definition of the investigator.

load_evidence -> assess_signals -> write_narrative -> verify_grounding -> (finalize
| write_narrative again, at most two LLM attempts | fallback_template -> finalize)
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph

from veedor.agents.investigation import obs
from veedor.agents.investigation.supervisor import (
    ASSEMBLE,
    InvestigationPorts,
    assemble_evidence,
    node_name,
    route_after_supervisor,
    run_specialist,
    supervisor,
)
from veedor.agents.investigator.nodes.assess_signals import assess_signals
from veedor.agents.investigator.nodes.fallback_template import fallback_template
from veedor.agents.investigator.nodes.finalize import finalize
from veedor.agents.investigator.nodes.load_evidence import EvidenceLoader, load_evidence
from veedor.agents.investigator.nodes.verify_grounding import verify_grounding
from veedor.agents.investigator.nodes.write_narrative import write_narrative
from veedor.agents.investigator.state import MAX_LLM_ATTEMPTS, InvestigatorState
from veedor.domain.investigation.vocab import SPECIALISTS
from veedor.infrastructure.llm.port import ChatModelPort

RECURSION_LIMIT = 60  # the supervisor loop adds up to 2 steps per dispatch (at most 6)


def route_after_verification(state: InvestigatorState) -> str:
    report = state.get("report")
    if report is not None and report.passed:
        return "finalize"
    if state.get("llm_used") and state.get("attempts", 0) < MAX_LLM_ATTEMPTS:
        return "write_narrative"
    return "fallback_template"


def _timed(name: str, fn: Callable[[InvestigatorState], dict]) -> Callable[[InvestigatorState], dict]:
    def run(state: InvestigatorState) -> dict[str, Any]:
        started = time.perf_counter()
        with obs.span(f"node {name}", node=name, ocid=state.get("ocid", "unknown")):
            update = fn(state)
        elapsed = (time.perf_counter() - started) * 1000
        timings = dict(state.get("timings_ms", {}))
        timings[name] = round(timings.get(name, 0.0) + elapsed, 2)
        return {**update, "timings_ms": timings}

    return run


def build_graph(
    *,
    loader: EvidenceLoader,
    chat_model: ChatModelPort | None,
    investigation: InvestigationPorts | None = None,
):
    graph = StateGraph(InvestigatorState)
    nodes: dict[str, Callable[[InvestigatorState], dict]] = {
        "load_evidence": partial(load_evidence, loader=loader),
        "assess_signals": assess_signals,
        "write_narrative": partial(write_narrative, chat_model=chat_model),
        "verify_grounding": verify_grounding,
        "fallback_template": fallback_template,
        "finalize": finalize,
    }
    if investigation is not None:
        nodes["supervisor"] = partial(supervisor, ports=investigation)
        nodes[ASSEMBLE] = partial(assemble_evidence, ports=investigation)
        for specialist in SPECIALISTS:
            nodes[node_name(specialist)] = partial(run_specialist, name=specialist, ports=investigation)
    for name, fn in nodes.items():
        graph.add_node(name, _timed(name, fn))
    graph.add_edge(START, "load_evidence")
    if investigation is None:
        graph.add_edge("load_evidence", "assess_signals")
    else:
        graph.add_edge("load_evidence", "supervisor")
        graph.add_conditional_edges(
            "supervisor",
            route_after_supervisor,
            {**{node_name(s): node_name(s) for s in SPECIALISTS}, ASSEMBLE: ASSEMBLE},
        )
        for specialist in SPECIALISTS:
            graph.add_edge(node_name(specialist), "supervisor")
        graph.add_edge(ASSEMBLE, "assess_signals")
    graph.add_edge("assess_signals", "write_narrative")
    graph.add_edge("write_narrative", "verify_grounding")
    graph.add_conditional_edges(
        "verify_grounding",
        route_after_verification,
        {
            "finalize": "finalize",
            "write_narrative": "write_narrative",
            "fallback_template": "fallback_template",
        },
    )
    graph.add_edge("fallback_template", "finalize")
    graph.add_edge("finalize", END)
    _register_node_names(nodes)
    return graph.compile()


def _register_node_names(nodes: dict[str, Callable[[InvestigatorState], dict]]) -> None:
    """Tell telemetry which node names are legitimate span/metric values (derived from the graph itself)."""
    try:
        from veedor.infrastructure.telemetry import register_vocabulary

        register_vocabulary(node=list(nodes))
    except Exception:  # noqa: BLE001 - telemetry is optional; the graph must still build without it
        return
