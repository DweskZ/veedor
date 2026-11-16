"""Dossier response schema (the content is produced and verified by `build_dossier`)."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import ConfigDict, Field

from veedor.schemas.common import MaskedModel


class DossierOut(MaskedModel):
    """Dossier with every string and nested field passed through the natural-person masking."""

    model_config = ConfigDict(extra="allow")
    mask_whole_payload: ClassVar[bool] = True

    ocid: str
    generated_at: str | None = None
    mode: str | None = Field(None, description="template | llm")
    summary_es: str | None = None
    sections: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    grounding_report: dict[str, Any] | None = None
