"""The supervisor node and its routing, the specialist nodes and the evidence assembly node."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from veedor.agents.investigation import obs
from veedor.agents.investigation.chooser import Chooser
from veedor.agents.investigation.specialists import SpecialistContext
from veedor.agents.investigation.subgraph import COMPILED, SPECIALIST_RECURSION_LIMIT
from veedor.agents.investigation.tools import RunBudget, ToolRunner
from veedor.agents.investigation.usage import UsageMeter
from veedor.agents.investigator.state import InvestigatorState
from veedor.domain.dossier.models import EvidencePack
from veedor.domain.investigation.assemble import assemble, facts_added
from veedor.domain.investigation.models import SpecialistRun, ToolCall
from veedor.domain.investigation.policies import (
    MAX_DISPATCHES,
    MAX_DISPATCHES_PER_SPECIALIST,
    Dispatch,
    DispatchRejected,
    check_dispatch,
    default_plan,
)
from veedor.domain.investigation.vocab import SPECIALISTS
from veedor.infrastructure.mcp.port import ToolBackend

ASSEMBLE = "assemble_evidence"


@dataclass
class InvestigationPorts:
    """Everything the investigation nodes need from the outside, injected so tests use fakes."""

    backend: ToolBackend
    chooser: Chooser
    meter: UsageMeter
    key_index: Any = None  # Callable[[], dict[str, frozenset[str]]] | None
    today: Any = date.today


def node_name(specialist: str) -> str:
    return f"{specialist}_agent"


def _summaries(state: InvestigatorState) -> dict[str, dict[str, Any]]:
    """Counters per specialist that has run: dispatches, calls and outcome counts (no text)."""
    out: dict[str, dict[str, Any]] = {}
    for run in state.get("inv_runs", []):
        item = out.setdefault(run.specialist, {"despachos": 0, "consultas": 0, "resultados": {}})
        item["despachos"] += 1
        item["consultas"] += run.n_tool_calls
        for outcome, count in run.outcomes.items():
            item["resultados"][outcome] = item["resultados"].get(outcome, 0) + count
    return out


def _valid(
    pack: EvidencePack, plan: list[Dispatch], dispatched: list[str], retryable: list[str] | None = None
) -> list[Dispatch]:
    """Keep the entries of a plan that respect the enumerations and the budgets.

    A repeat dispatch of a specialist is honoured only when its previous run ended with a retryable
    failure (`retryable`); otherwise it is ignored, not an error.
    """
    kept: list[Dispatch] = []
    seen = list(dispatched)
    for item in plan:
        if item.specialist in seen and item.specialist not in (retryable or []):
            continue
        try:
            check_dispatch(item.specialist, item.reason, pack, seen)
        except DispatchRejected:
            continue
        seen.append(item.specialist)
        kept.append(item)
    return kept


def _retry_candidates(state: InvestigatorState) -> list[str]:
    dispatched = state.get("inv_dispatched", [])
    if len(dispatched) >= MAX_DISPATCHES:
        return []
    return [
        name
        for name, actions in state.get("inv_retry", {}).items()
        if actions and dispatched.count(name) < MAX_DISPATCHES_PER_SPECIALIST
    ]


def supervisor(state: InvestigatorState, *, ports: InvestigationPorts) -> dict[str, Any]:
    pack = state["pack"]
    dispatched = list(state.get("inv_dispatched", []))
    queue = list(state.get("inv_queue", []))
    decisions = list(state.get("inv_decisions", []))
    update: dict[str, Any] = {}

    if not state.get("inv_planned"):
        model_plan = ports.chooser.dispatches(pack, dispatched, {})
        plan = model_plan if model_plan is not None else default_plan(pack)
        by = "model" if model_plan is not None else "policy"
        queue = [(d.specialist, d.reason, by) for d in _valid(pack, plan, dispatched)]
        decisions.append({"step": "plan", "by": by, "n": str(len(queue))})
        update["inv_planned"] = True

    if not queue and not state.get("inv_reviewed"):
        update["inv_reviewed"] = True
        candidates = _retry_candidates(state)
        if candidates:
            model_plan = ports.chooser.dispatches(pack, dispatched, _summaries(state), allowed=candidates)
            by = "model" if model_plan is not None else "policy"
            plan = (
                model_plan
                if model_plan is not None
                else [
                    Dispatch(name, "retry_after_transient_failure")
                    for name in candidates  # type: ignore[arg-type]
                ]
            )
            queue = [(d.specialist, d.reason, by) for d in _valid(pack, plan, dispatched, candidates)]
            decisions.append({"step": "review", "by": by, "n": str(len(queue))})

    update["inv_decisions"] = decisions
    if queue:
        (name, reason, by), *rest = queue
        update.update(
            inv_next=name, inv_next_reason=reason, inv_next_by=by, inv_queue=rest,
            inv_dispatched=[*dispatched, name],
        )  # fmt: skip
    else:
        update.update(inv_next=None, inv_queue=[])
    return update


def route_after_supervisor(state: InvestigatorState) -> str:
    name = state.get("inv_next")
    return node_name(name) if name in SPECIALISTS else ASSEMBLE


def _merge(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """A re-dispatch replaces a finding only when it is not worse than what is already known."""
    merged = dict(old)
    for key, value in new.items():
        previous = merged.get(key)
        if previous is None or getattr(previous, "outcome", None) != "ok" or value.outcome == "ok":
            merged[key] = value
    return merged


def run_specialist(state: InvestigatorState, *, name: str, ports: InvestigationPorts) -> dict[str, Any]:
    pack = state["pack"]
    log: list[ToolCall] = []
    ctx = SpecialistContext(
        pack=pack,
        runner=ToolRunner(ports.backend, log, pack.process.ocid),
        budget=RunBudget(),
        today=ports.today(),
        key_index=ports.key_index,
    )
    retry = state.get("inv_retry", {}).get(name)
    first_run = name not in {r.specialist for r in state.get("inv_runs", [])}
    offered = None if first_run or not retry else list(retry)
    with obs.span("specialist", ocid=pack.process.ocid, specialist=name):
        result = COMPILED[name].invoke(
            {"offered": offered} if offered else {},
            config={
                "configurable": {"ctx": ctx, "chooser": ports.chooser},
                "recursion_limit": SPECIALIST_RECURSION_LIMIT,
            },
        )
    outcomes: dict[str, int] = {}
    for call in log:
        outcomes[call.outcome] = outcomes.get(call.outcome, 0) + 1
    run = SpecialistRun(
        specialist=name,
        dispatch_reason=state.get("inv_next_reason", "baseline_check"),
        decided_by=state.get("inv_next_by", "policy"),  # type: ignore[arg-type]
        n_tool_calls=ctx.budget.used,
        outcomes=outcomes,
        action_plan_by=result.get("plan_by", "policy"),
    )
    failed = {call.outcome for call in log} & {"timeout", "upstream_error", "invalid_result"}
    obs.record_specialist_run(name, "ok" if not failed else "partial")
    retry_map = dict(state.get("inv_retry", {}))
    retry_map[name] = ctx.failed_actions
    return {
        "inv_runs": [*state.get("inv_runs", []), run],
        "inv_log": [*state.get("inv_log", []), *log],
        "inv_findings": _merge(state.get("inv_findings", {}), ctx.findings),
        "inv_retry": retry_map,
    }


def assemble_evidence(state: InvestigatorState, *, ports: InvestigationPorts) -> dict[str, Any]:
    today = ports.today()
    pack = assemble(
        state["pack"],
        state.get("inv_findings", {}),
        state.get("inv_log", []),
        state.get("inv_runs", []),
        today,
    )
    added = facts_added(pack)
    runs = [
        run.model_copy(update={"facts_added": added.get(run.specialist, [])})
        for run in state.get("inv_runs", [])
    ]
    return {"pack": pack, "inv_runs": runs, "inv_added": added}


def now() -> datetime:
    return datetime.now(UTC)
