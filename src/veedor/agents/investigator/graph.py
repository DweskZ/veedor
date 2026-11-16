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

from veedor.agents.investigator.nodes.assess_signals import assess_signals
from veedor.agents.investigator.nodes.fallback_template import fallback_template
from veedor.agents.investigator.nodes.finalize import finalize
from veedor.agents.investigator.nodes.load_evidence import EvidenceLoader, load_evidence
from veedor.agents.investigator.nodes.verify_grounding import verify_grounding
from veedor.agents.investigator.nodes.write_narrative import write_narrative
from veedor.agents.investigator.state import MAX_LLM_ATTEMPTS, InvestigatorState
from veedor.infrastructure.llm.port import ChatModelPort

RECURSION_LIMIT = 20


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
        update = fn(state)
        elapsed = (time.perf_counter() - started) * 1000
        timings = dict(state.get("timings_ms", {}))
        timings[name] = round(timings.get(name, 0.0) + elapsed, 2)
        return {**update, "timings_ms": timings}

    return run


def build_graph(*, loader: EvidenceLoader, chat_model: ChatModelPort | None):
    graph = StateGraph(InvestigatorState)
    nodes = {
        "load_evidence": partial(load_evidence, loader=loader),
        "assess_signals": assess_signals,
        "write_narrative": partial(write_narrative, chat_model=chat_model),
        "verify_grounding": verify_grounding,
        "fallback_template": fallback_template,
        "finalize": finalize,
    }
    for name, fn in nodes.items():
        graph.add_node(name, _timed(name, fn))
    graph.add_edge(START, "load_evidence")
    graph.add_edge("load_evidence", "assess_signals")
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
    return graph.compile()
