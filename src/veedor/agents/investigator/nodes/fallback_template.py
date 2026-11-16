"""Deterministic fallback after the model failed, or when the template itself cannot be verified."""

from __future__ import annotations

from veedor.agents.investigator.nodes.verify_grounding import narrative_text
from veedor.agents.investigator.state import InvestigatorState
from veedor.domain.dossier.grounding import verify
from veedor.domain.dossier.template import (
    bare_narrative,
    minimal_narrative,
    render_template,
    ultra_minimal_narrative,
)


def fallback_template(state: InvestigatorState) -> dict:
    """Template, then a facts-only minimal dossier, then an identity-only one. Never raises."""
    pack = state["pack"]
    if state.get("llm_used"):
        reason = f"LLM no superó la verificación tras {state.get('attempts', 0)} intento(s)"
    else:
        reason = None
    narrative = render_template(pack)
    report = verify(narrative_text(narrative), pack)
    mode = "template"
    if not report.passed:
        failed = [f"{t.kind}:{t.text[:40]}" for t in report.unsupported + report.forbidden][:5]
        reason = f"{reason + '; ' if reason else ''}la plantilla no superó la verificación ({failed})"
        mode = "template_minimal"
        for build in (minimal_narrative, ultra_minimal_narrative, bare_narrative):
            narrative = build(pack)
            report = verify(narrative_text(narrative), pack)
            if report.passed:
                break
    return {"narrative": narrative, "mode": mode, "report": report, "fallback_reason": reason}
