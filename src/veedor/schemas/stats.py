"""Stats endpoint schema."""

from __future__ import annotations

from pydantic import BaseModel, Field

from veedor.schemas.buyers import SignalCount


class ScoreBucket(BaseModel):
    lower: int = Field(description="Inclusive lower bound of the bucket.")
    upper: int = Field(description="Exclusive upper bound (the last bucket includes 100).")
    count: int


class Stats(BaseModel):
    processes_total: int | None = Field(None, description="Rows in the lake (None when not available).")
    processes_by_method_group: dict[str, int] = {}
    processes_scored: int | None = None
    processes_with_signals: int | None = None
    mean_risk_score: float | None = None
    score_distribution: list[ScoreBucket] = []
    signal_counts: list[SignalCount] = Field([], description="Risk signals only.")
    context_signal_counts: list[SignalCount] = Field([], description="Context signals (not in the score).")
    first_year: int | None = None
    last_year: int | None = None
    last_data_date: str | None = None
    available_tables: dict[str, bool]
