"""Row counts for the registry tables in the lake."""

from __future__ import annotations

from pathlib import Path

import duckdb

from veedor.infrastructure.registries.common import sql_str

REGISTRY_TABLES = ("suppliers_sri", "ghost_companies", "companies_supercias", "company_financials")


def table_counts(lake_dir: Path) -> dict[str, int | None]:
    """Row count per registry table, or None when the Parquet file does not exist."""
    con = duckdb.connect()
    counts: dict[str, int | None] = {}
    for table in REGISTRY_TABLES:
        path = lake_dir / f"{table}.parquet"
        counts[table] = (
            con.execute(f"SELECT count(*) FROM read_parquet({sql_str(path)})").fetchone()[0]
            if path.exists()
            else None
        )
    return counts
