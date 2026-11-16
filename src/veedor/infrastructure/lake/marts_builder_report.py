"""Read-side helpers for the marts the builder writes: build summary and top-risk listing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import orjson

from veedor.infrastructure.lake.connection import quote_literal
from veedor.infrastructure.lake.marts_builder import SUMMARY_NAME


class MartsNotBuiltError(RuntimeError):
    """Raised when a mart file is missing."""


class DuckDbMartsReport:
    def __init__(self, marts_dir: Path) -> None:
        self._dir = marts_dir

    def summary(self) -> dict[str, Any]:
        path = self._dir / SUMMARY_NAME
        if not path.is_file():
            raise MartsNotBuiltError(f"{path} not found. Run `veedor signals build` first.")
        return orjson.loads(path.read_bytes())

    def top(self, limit: int, year: int | None = None, method: str | None = None) -> list[dict[str, Any]]:
        path = self._dir / "process_scores.parquet"
        if not path.is_file():
            raise MartsNotBuiltError(f"{path} not found. Run `veedor signals build` first.")
        where, params = ["risk_score > 0"], []
        if year is not None:
            where.append("year = ?")
            params.append(year)
        if method:
            where.append("method = ?")
            params.append(method)
        sql = (
            "SELECT ocid, year, method, buyer_name, winner_name, winner_kind, award_total, risk_score, "
            "signal_codes, anomaly_score "
            f"FROM read_parquet({quote_literal(str(path))}) WHERE {' AND '.join(where)} "
            "ORDER BY risk_score DESC, n_signals DESC, award_total DESC NULLS LAST, ocid LIMIT ?"
        )
        con = duckdb.connect(":memory:")
        try:
            cursor = con.execute(sql, [*params, limit])
            names = [c[0] for c in cursor.description]
            return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
        finally:
            con.close()
