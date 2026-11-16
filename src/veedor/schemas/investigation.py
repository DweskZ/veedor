"""Stored investigation response (produced by the CLI, served read-only)."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import ConfigDict

from veedor.schemas.common import MaskedModel


class InvestigationOut(MaskedModel):
    """The stored record with every string and nested field passed through the natural-person masking."""

    model_config = ConfigDict(extra="allow")
    mask_whole_payload: ClassVar[bool] = True

    ocid: str
    started_at: str | None = None
    finished_at: str | None = None
    renderer_version: int | None = None
    specialists: list[dict[str, Any]] = []
    tool_log: list[dict[str, Any]] = []
    facts_added: list[str] = []
    dossier: dict[str, Any] | None = None
    model_usage: dict[str, Any] | None = None
