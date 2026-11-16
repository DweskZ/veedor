"""Grounding gate: the real defence against hallucinated or injected content."""

from __future__ import annotations

from veedor.agents.investigation import obs
from veedor.agents.investigator.state import InvestigatorState
from veedor.domain.dossier.grounding import verify


def narrative_text(narrative) -> str:  # noqa: ANN001
    return "\n".join([narrative.summary_es, *[f"{s.title}\n{s.body}" for s in narrative.sections]])


def verify_grounding(state: InvestigatorState) -> dict:
    narrative = state.get("narrative")
    log = list(state.get("attempt_log", []))
    if narrative is None:
        error = state.get("attempt_log_error") or "sin texto"
        log.append({"attempt": state.get("attempts", 0), "passed": False, "reason": error, "rejected": []})
        return {"report": None, "attempt_log": log, "rejected": state.get("rejected", [])}
    report = verify(narrative_text(narrative), state["pack"])
    obs.record_grounding(report.passed, state.get("mode", "template"))
    rejected = [t.text for t in report.unsupported + report.forbidden]
    if state.get("llm_used"):
        log.append(
            {
                "attempt": state.get("attempts", 0),
                "passed": report.passed,
                "reason": None,
                "rejected": rejected[:10],
            }
        )
    return {"report": report, "rejected": rejected, "attempt_log": log}
