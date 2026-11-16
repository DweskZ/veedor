"""A specialist as a LangGraph subgraph: choose actions -> act (loop) -> done.

The subgraph is compiled once per specialist. Everything that is not plain data (the tool runner, the
chooser, the pack) travels in `config["configurable"]`, never in the state.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from veedor.agents.investigation import obs
from veedor.agents.investigation.chooser import Chooser
from veedor.agents.investigation.specialists import SPECIALISTS, SpecialistContext, SpecialistSpec
from veedor.domain.investigation.policies import ACTION_MENU, Action

SPECIALIST_RECURSION_LIMIT = 20


class SpecialistState(TypedDict, total=False):
    offered: list[str]  # action ids this dispatch may run (all of them, or only the ones to retry)
    queue: list[str]
    done: list[str]
    plan_by: str


def _choose(state: SpecialistState, config: RunnableConfig, *, spec: SpecialistSpec) -> dict[str, Any]:
    chooser: Chooser = config["configurable"]["chooser"]
    menu = {a.id: a for a in ACTION_MENU[spec.name]}  # type: ignore[index]
    offered = [menu[i] for i in state.get("offered", list(menu)) if i in menu]
    chosen: list[Action] | None = chooser.actions(spec.name, offered)
    by = "model" if chosen is not None else "policy"
    return {"queue": [a.id for a in (chosen if chosen is not None else offered)], "plan_by": by, "done": []}


def _act(state: SpecialistState, config: RunnableConfig, *, spec: SpecialistSpec) -> dict[str, Any]:
    ctx: SpecialistContext = config["configurable"]["ctx"]
    queue = list(state.get("queue", []))
    action_id = queue.pop(0)
    with obs.span("specialist action", ocid=ctx.pack.process.ocid, specialist=spec.name):
        spec.handlers[action_id](ctx)
    return {"queue": queue, "done": [*state.get("done", []), action_id]}


def _more(state: SpecialistState) -> str:
    return "act" if state.get("queue") else END


def build_specialist_graph(spec: SpecialistSpec):  # noqa: ANN201
    graph = StateGraph(SpecialistState)
    graph.add_node("choose", lambda state, config: _choose(state, config, spec=spec))
    graph.add_node("act", lambda state, config: _act(state, config, spec=spec))
    graph.add_edge(START, "choose")
    graph.add_conditional_edges("choose", _more, {"act": "act", END: END})
    graph.add_conditional_edges("act", _more, {"act": "act", END: END})
    return graph.compile()


COMPILED = {name: build_specialist_graph(spec) for name, spec in SPECIALISTS.items()}
