"""Narrative writer.

With an LLM configured the model returns a *plan* (fact ids, order, closed-set choices); the renderer
writes every sentence from the template catalogue. Without one, the full template is rendered.
"""

from __future__ import annotations

from veedor.agents.investigator.outputs import OutputRejected, parse_plan, screen
from veedor.agents.investigator.prompting import system_prompt, user_prompt
from veedor.agents.investigator.state import InvestigatorState
from veedor.domain.dossier.plan import PlanError
from veedor.domain.dossier.template import render_plan, render_template
from veedor.infrastructure.llm.port import ChatModelPort


def write_narrative(state: InvestigatorState, *, chat_model: ChatModelPort | None) -> dict:
    pack = state["pack"]
    if chat_model is None:
        return {"narrative": render_template(pack), "mode": "template", "llm_used": False}

    attempts = state.get("attempts", 0) + 1
    update: dict = {"attempts": attempts, "llm_used": True, "model": chat_model.model_name}
    try:
        response = chat_model.complete(system_prompt(), user_prompt(pack, state.get("rejected")))
    except Exception as exc:  # noqa: BLE001 - any provider failure degrades to the template
        return {**update, "narrative": None, "rejected": [], "attempt_log_error": type(exc).__name__}
    update["prompt_tokens"] = state.get("prompt_tokens", 0) + (response.prompt_tokens or 0)
    update["completion_tokens"] = state.get("completion_tokens", 0) + (response.completion_tokens or 0)
    try:
        plan = parse_plan(response.text)
        screen(plan)
        narrative = render_plan(pack, plan.to_render_plan())
    except (OutputRejected, PlanError) as exc:
        return {**update, "narrative": None, "rejected": [str(exc)], "attempt_log_error": str(exc)}
    return {**update, "narrative": narrative, "mode": "llm", "attempt_log_error": None}
