"""Typed records of an investigation: tool log, specialist runs, supervisor decisions, stored record."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from veedor.domain.dossier.models import Dossier, LookupOutcome

DecidedBy = Literal["policy", "model"]


class ToolCall(BaseModel):
    """One tool call. Holds no identifier of the target, only its reference (``winner``...)."""

    specialist: str
    tool: str
    target: str  # reference into the pack: winner | buyer | process
    started_at: datetime
    ended_at: datetime
    duration_ms: float
    outcome: LookupOutcome
    attempts: int = 1
    reason: str | None = None  # closed vocabulary (`vocab.Reason`)


class SpecialistRun(BaseModel):
    specialist: str
    dispatch_reason: str  # closed vocabulary (`vocab.DispatchReason`)
    decided_by: DecidedBy
    n_tool_calls: int
    outcomes: dict[str, int] = Field(default_factory=dict)
    facts_added: list[str] = Field(default_factory=list)  # catalogue fact ids
    action_plan_by: DecidedBy = "policy"


class ModelUsage(BaseModel):
    model: str | None = None
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    invalid_choices: int = 0  # model answers rejected by validation


class InvestigationRecord(BaseModel):
    """What `data/investigations/<ocid>.json` stores."""

    ocid: str
    started_at: datetime
    finished_at: datetime
    renderer_version: int
    specialists: list[SpecialistRun] = Field(default_factory=list)
    tool_log: list[ToolCall] = Field(default_factory=list)
    facts_added: list[str] = Field(default_factory=list)
    dossier: Dossier | None = None  # None only when the record is withheld
    withheld: str | None = None  # closed reason; set when the privacy guard refused the full record
    model_usage: ModelUsage = Field(default_factory=ModelUsage)
