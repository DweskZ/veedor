"""Human review schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReviewStatus(StrEnum):
    pending = "pending"
    confirmed_signal = "confirmed_signal"
    dismissed = "dismissed"


class ReviewCreate(BaseModel):
    status: ReviewStatus = Field(examples=["confirmed_signal"])
    note: str | None = Field(
        None, max_length=2000, examples=["Revisé las bases: el plazo coincide con el indicador."]
    )
    reviewer: str | None = Field(None, max_length=120, examples=["analista.1"])


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ocid: str
    status: ReviewStatus
    note: str | None = None
    reviewer: str | None = None
    created_at: datetime
