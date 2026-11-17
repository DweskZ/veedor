"""Builds ``threshold_context.parquet``: verified yearly thresholds with band counts and bunching.

Context only. Nothing here feeds the signals table or any score. One row per verified year and
threshold (see ``veedor.domain.thresholds``). Budget is the amount that decides the procedure, so the
bands are over ``processes.budget``. Parameterised SQL only.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from veedor.domain import thresholds as th
from veedor.domain.bunching import BunchingSpec, estimate_bunching

BAND = 0.05
MART_NAME = "threshold_context.parquet"
SEED = 20260101

CAVEATS = (
    "Context only: not a risk signal and not part of any score.",
    "Bunching below a threshold is a description of the budget distribution; it can come from contract "
    "splitting or from real purchasing distortion, and neither is identified here.",
    "The counterfactual is a fitted polynomial; round-number budgets and the shape of demand can move it.",
)
NOT_ANALYSABLE_NOTE = (
    "Ínfima cuantía processes are not in the open data used, so only the counts just above the "
    "threshold are shown and no bunching estimate is computed."
)

LOAD_SQL = """
SELECT year, method, category, budget, award_total, coalesce(buyer_ruc, '<missing>') AS buyer, buyer_name
FROM read_parquet($path)
WHERE method_group = 'competitive' AND budget > 0 AND year IS NOT NULL AND list_contains($years, year)
"""


def load_budgets(lake_dir: Path, years: Sequence[int]) -> dict[str, np.ndarray]:
    """Competitive processes of the verified years, as arrays (no identifiers beyond the buyer id)."""
    con = duckdb.connect()
    rel = con.execute(LOAD_SQL, {"path": str(lake_dir / "processes.parquet"), "years": list(years)})
    cols = [c[0] for c in rel.description]
    rows = rel.fetchall()
    data = {c: np.asarray([r[i] for r in rows], dtype=object) for i, c in enumerate(cols)}
    data["year"] = data["year"].astype(int)
    data["budget"] = data["budget"].astype(float)
    data["award_total"] = np.asarray([np.nan if v is None else v for v in data["award_total"]], dtype=float)
    data["cat"] = np.asarray(
        [th.category_of(c, m) for c, m in zip(data["category"], data["method"], strict=True)], dtype=object
    )
    return data


def select(data: dict[str, np.ndarray], t: th.Threshold) -> np.ndarray:
    """Mask of the processes governed by threshold ``t`` (year, category, procedures on either side)."""
    methods = set(t.below) | set(t.above)
    return (
        (data["year"] == t.year)
        & (data["cat"] == t.category)
        & np.isin(data["method"].astype(str), list(methods))
    )


def relative_amounts(data: dict[str, np.ndarray], mask: np.ndarray, value: float) -> np.ndarray:
    return data["budget"][mask] / value - 1.0


def band_counts(relative: np.ndarray) -> tuple[int, int]:
    below = int(((relative > -BAND) & (relative <= 0)).sum())
    above = int(((relative > 0) & (relative <= BAND)).sum())
    return below, above


def build_rows(lake_dir: Path, n_boot: int = 500, seed: int = SEED) -> list[dict[str, Any]]:
    rules = th.all_thresholds()
    data = load_budgets(lake_dir, sorted({t.year for t in rules}))
    rows = []
    for t in rules:
        mask = select(data, t)
        rel = relative_amounts(data, mask, t.value_usd)
        below, above = band_counts(rel)
        row: dict[str, Any] = {
            "year": t.year,
            "category": t.category,
            "threshold_code": t.code,
            "procedure_below": t.procedure_below_label,
            "procedure_above": t.procedure_above_label,
            "coefficient": t.coefficient,
            "threshold_usd": t.value_usd,
            "regime": t.regime,
            "source_url": t.source_url,
            "source_note": t.source_note,
            "verification": "verified_official_source",
            "analysed": t.analysable,
            "applies_to_methods": "|".join(sorted(set(t.below) | set(t.above))),
            "n_band_below": below,
            "n_band_above": above,
            "n_window": 0,
            "status": "not_analysable",
            "excess_bins": None,
            "excess_bins_low": None,
            "excess_bins_high": None,
            "excess_pct": None,
            "missing_above_pct": None,
            "caveat": NOT_ANALYSABLE_NOTE,
        }
        if t.analysable:
            est = estimate_bunching(rel, data["buyer"][mask], BunchingSpec(), n_boot, seed)
            row["n_window"], row["status"] = est["n_window"], est["status"]
            row["caveat"] = " ".join(CAVEATS)
            if est["status"] == "estimated":
                row["excess_bins"] = est["excess_bins"]
                row["excess_bins_low"], row["excess_bins_high"] = est["excess_bins_ci"]
                row["excess_pct"] = est["excess_pct"]
                row["missing_above_pct"] = est["missing_above_pct"]
        rows.append(row)
    return rows


def write_mart(rows: list[dict[str, Any]], marts_dir: Path) -> Path:
    marts_dir.mkdir(parents=True, exist_ok=True)
    target = marts_dir / MART_NAME
    tmp = target.with_suffix(".tmp")
    pq.write_table(pa.Table.from_pylist(rows), tmp)
    tmp.replace(target)
    return target


def build_threshold_context(lake_dir: Path, marts_dir: Path, n_boot: int = 500) -> Path:
    return write_mart(build_rows(lake_dir, n_boot), marts_dir)
