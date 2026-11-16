"""Typed state of the investigator graph."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from veedor.domain.dossier.models import Dossier, EvidencePack, GroundingReport
from veedor.domain.dossier.template import Narrative

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
