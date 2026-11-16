"""Application service for the Signals v1 marts: build, read the summary, list top processes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class MartsBuilder(Protocol):
    def __call__(self, lake_dir: Path, marts_dir: Path) -> dict[str, Any]: ...


class MartsReport(Protocol):
    def summary(self) -> dict[str, Any]: ...

    def top(self, limit: int, year: int | None, method: str | None) -> list[dict[str, Any]]: ...


def build_marts(builder: MartsBuilder, lake_dir: Path, marts_dir: Path) -> dict[str, Any]:
    """Run a full build and return the summary."""
    return builder(lake_dir, marts_dir)


def get_build_summary(report: MartsReport) -> dict[str, Any]:
    return report.summary()


def top_risk_processes(
    report: MartsReport, limit: int = 20, year: int | None = None, method: str | None = None
) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    return report.top(limit, year, method)
