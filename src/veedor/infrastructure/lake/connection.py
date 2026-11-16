"""DuckDB access to the Parquet lake: one in-memory connection with a view per existing table."""

from __future__ import annotations

from pathlib import Path

import duckdb

from veedor.core.settings import get_settings

CORE_TABLES = ("processes", "tenderers", "awards")
REGISTRY_TABLES = ("suppliers_sri", "ghost_companies", "companies_supercias", "company_financials")
LAKE_TABLES = CORE_TABLES + REGISTRY_TABLES


def parquet_path(lake_dir: Path, table: str) -> Path:
    return lake_dir / f"{table}.parquet"


def existing_tables(lake_dir: Path) -> list[str]:
    """Names of the lake tables whose Parquet file is present."""
    return [t for t in LAKE_TABLES if parquet_path(lake_dir, t).is_file()]


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def connect_lake(
    lake_dir: Path | None = None,
    *,
    threads: int | None = None,
    memory_limit: str | None = None,
    temp_dir: Path | None = None,
) -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB connection exposing every present lake table as a view."""
    lake_dir = lake_dir or get_settings().lake_dir
    con = duckdb.connect(":memory:")
    if threads:
        con.execute(f"SET threads TO {int(threads)}")
    if memory_limit:
        con.execute("SET memory_limit = " + quote_literal(memory_limit))
    if temp_dir:
        temp_dir.mkdir(parents=True, exist_ok=True)
        con.execute("SET temp_directory = " + quote_literal(str(temp_dir)))
    for table in existing_tables(lake_dir):
        path = quote_literal(str(parquet_path(lake_dir, table)))
        con.execute(f'CREATE VIEW "{table}" AS SELECT * FROM read_parquet({path})')
    return con


def view_columns(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    rows = con.execute(f'DESCRIBE "{table}"').fetchall()
    return {row[0] for row in rows}
