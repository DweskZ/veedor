"""Assemble the dossier. Text that failed verification is never stored."""

from __future__ import annotations

from datetime import UTC, datetime

from veedor.agents.investigator.state import InvestigatorState
from veedor.domain.dossier.errors import GroundingError
from veedor.domain.dossier.models import Dossier
from veedor.domain.dossier.version import RENDERER_VERSION


def finalize(state: InvestigatorState) -> dict:
    report, narrative, pack = state.get("report"), state.get("narrative"), state["pack"]
    if report is None or narrative is None or not report.passed:
        raise GroundingError(f"Refusing to store an unverified dossier for {state['ocid']}")
    dossier = Dossier(
        ocid=state["ocid"],
        generated_at=datetime.now(UTC),
        mode=state["mode"],
        summary_es=narrative.summary_es,
        sections=narrative.sections,
        sources=pack.sources,
        grounding_report=report,
        llm_attempts=state.get("attempts", 0),
        renderer_version=RENDERER_VERSION,
        fallback_reason=state.get("fallback_reason"),
    )
    return {"dossier": dossier}
