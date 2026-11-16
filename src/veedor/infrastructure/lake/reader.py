"""Read-only DuckDB access to the Parquet lake and marts."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb

from veedor.use_cases.queries.ports import LakeUnavailableError, Row

LAKE_TABLES = (
    "processes",
    "tenderers",
    "awards",
    "suppliers_sri",
    "ghost_companies",
    "companies_supercias",
    "company_financials",
)
OPEN_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 0.15
logger = logging.getLogger(__name__)
MART_TABLES = ("process_signals", "process_scores", "supplier_profiles")


class LakeReader:
    """Registers each requested Parquet file as a view in a throw-away in-memory connection.

    Statements must be single SELECT/WITH queries; values are always bound parameters.
    """

    def __init__(self, lake_dir: Path, marts_dir: Path) -> None:
        self._allowed = sorted({str(lake_dir.resolve()), str(marts_dir.resolve())})
        self._paths = {name: lake_dir / f"{name}.parquet" for name in LAKE_TABLES}
        self._paths |= {name: marts_dir / f"{name}.parquet" for name in MART_TABLES}

    def has_table(self, name: str) -> bool:
        path = self._paths.get(name)
        return path is not None and path.is_file()

    def availability(self) -> dict[str, bool]:
        return {name: self.has_table(name) for name in self._paths}

    def _lock_down(self, connection: duckdb.DuckDBPyConnection) -> None:
        """Only the lake and marts directories stay readable; no other file, URL or write.

        `allowed_directories` must be set before `enable_external_access=false`, and
        `lock_configuration` stops a query from undoing either setting.
        """
        allowed = ", ".join("'" + path.replace("'", "''") + "'" for path in self._allowed)
        connection.execute(f"SET allowed_directories=[{allowed}]")
        connection.execute("SET enable_external_access=false")
        connection.execute("SET lock_configuration=true")

    def fetch(self, sql: str, params: Sequence[Any] = (), *, tables: Sequence[str]) -> list[Row]:
        missing = [name for name in tables if not self.has_table(name)]
        if missing:
            raise LakeUnavailableError(missing)
        if not sql.lstrip().lower().startswith(("select", "with")):
            raise ValueError("Only SELECT statements are allowed")
        for attempt in range(OPEN_ATTEMPTS):
            try:
                return self._run(sql, params, tables)
            except duckdb.IOException as exc:  # transient open failure (e.g. "Permission denied" in a burst)
                if attempt + 1 == OPEN_ATTEMPTS:
                    logger.warning("Lake read failed after %d attempts: %s", OPEN_ATTEMPTS, exc)
                    raise LakeUnavailableError(tables) from exc
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        raise AssertionError("unreachable")  # pragma: no cover

    def _run(self, sql: str, params: Sequence[Any], tables: Sequence[str]) -> list[Row]:
        connection = duckdb.connect(":memory:")
        try:
            for name in dict.fromkeys(tables):
                literal = str(self._paths[name]).replace("'", "''")
                connection.execute(f"CREATE VIEW \"{name}\" AS SELECT * FROM read_parquet('{literal}')")
            self._lock_down(connection)
            cursor = connection.execute(sql, list(params))
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, record, strict=True)) for record in cursor.fetchall()]
        finally:
            connection.close()
