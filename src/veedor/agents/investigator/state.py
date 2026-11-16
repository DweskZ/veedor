"""Typed state of the investigator graph."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from veedor.domain.dossier.models import Dossier, EvidencePack, GroundingReport
from veedor.domain.dossier.template import Narrative
from veedor.domain.investigation.models import SpecialistRun, ToolCall

MAX_LLM_ATTEMPTS = 2


class InvestigatorState(TypedDict, total=False):
    ocid: str
    pack: EvidencePack
    narrative: Narrative | None
    mode: Literal["template", "template_minimal", "llm"]
    llm_used: bool
    attempts: int
    rejected: list[str]
    report: GroundingReport | None
    fallback_reason: str | None
    attempt_log: list[dict[str, Any]]
    attempt_log_error: str | None
    prompt_tokens: int
    completion_tokens: int
    model: str | None
    timings_ms: dict[str, float]
    dossier: Dossier
    # investigation (stage 2); absent when the graph is built without investigation ports
    inv_planned: bool
    inv_reviewed: bool
    inv_queue: list[tuple[str, str, str]]  # (specialist, dispatch reason, decided by)
    inv_dispatched: list[str]
    inv_next: str | None
    inv_next_reason: str
    inv_next_by: str
    inv_runs: list[SpecialistRun]
    inv_log: list[ToolCall]
    inv_findings: dict[str, Any]
    inv_retry: dict[str, list[str]]  # specialist -> actions that ended in a timeout
    inv_decisions: list[dict[str, str]]
    inv_added: dict[str, list[str]]
