"""Read-only DuckDB access to the Parquet lake and marts."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import lru_cache
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
DEFAULT_THREADS = 2
REFRESH_INTERVAL_SECONDS = 1.0  # how often the files are re-checked for a rebuild
SUMMARY_NAME = "build_summary.json"
logger = logging.getLogger(__name__)


@lru_cache(maxsize=512)
def _check_read_only(sql: str) -> None:
    """Accept exactly one SELECT/WITH statement. The database is shared by every request, so a
    stacked ``...; CREATE VIEW ...`` would outlive the call that sent it."""
    statements = duckdb.extract_statements(sql)
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        raise ValueError("Only a single SELECT statement is allowed")


MART_TABLES = ("process_signals", "process_scores", "supplier_profiles")


class LakeReader:
    """One locked-down in-memory DuckDB database per process, queried through a cursor per call.

    The database holds a view over every Parquet file present, created once. DuckDB's Python
    client does not support concurrent use of one connection object from several threads; the
    documented pattern is one ``cursor()`` per thread (a new connection to the same database,
    sharing its views and its locked configuration), so each call takes and closes its own.
    When a Parquet file or ``build_summary.json`` is replaced on disk (a marts rebuild) a fresh
    database is built and swapped in; calls already running finish on the old one.

    Statements must be single SELECT/WITH queries; values are always bound parameters.
    """

    def __init__(
        self,
        lake_dir: Path,
        marts_dir: Path,
        *,
        threads: int = DEFAULT_THREADS,
        refresh_interval: float = REFRESH_INTERVAL_SECONDS,
    ) -> None:
        self._allowed = sorted({str(lake_dir.resolve()), str(marts_dir.resolve())})
        self._paths = {name: lake_dir / f"{name}.parquet" for name in LAKE_TABLES}
        self._paths |= {name: marts_dir / f"{name}.parquet" for name in MART_TABLES}
        self._summary_path = marts_dir / SUMMARY_NAME
        self._threads = max(1, int(threads))
        self._refresh_interval = refresh_interval
        self._lock = threading.Lock()
        self._database: duckdb.DuckDBPyConnection | None = None
        self._registered: frozenset[str] = frozenset()
        self._signature: tuple = ()
        self._checked_at = 0.0

    def has_table(self, name: str) -> bool:
        path = self._paths.get(name)
        return path is not None and path.is_file()

    def availability(self) -> dict[str, bool]:
        return {name: self.has_table(name) for name in self._paths}

    def data_version(self) -> str:
        """Identity of the data on disk: changes whenever a table or the build summary is replaced."""
        return repr(self._file_signature())

    def built_at(self) -> str | None:
        """UTC modification time of ``build_summary.json`` (when the marts were last built)."""
        try:
            stamp = self._summary_path.stat().st_mtime
        except OSError:
            return None
        return datetime.fromtimestamp(stamp, tz=UTC).isoformat(timespec="seconds")

    def _file_signature(self) -> tuple:
        entries: list[tuple] = []
        for path in (*sorted(self._paths.values()), self._summary_path):
            try:
                info = path.stat()
            except OSError:
                entries.append((str(path), None, None))
            else:
                entries.append((str(path), info.st_mtime_ns, info.st_size))
        return tuple(entries)

    def _lock_down(self, connection: duckdb.DuckDBPyConnection) -> None:
        """Only the lake and marts directories stay readable; no other file, URL or write.

        `allowed_directories` must be set before `enable_external_access=false`, and
        `lock_configuration` stops a query from undoing either setting. The thread bound is set
        first because the lock freezes it too.
        """
        allowed = ", ".join("'" + path.replace("'", "''") + "'" for path in self._allowed)
        connection.execute(f"SET threads={self._threads}")
        connection.execute(f"SET allowed_directories=[{allowed}]")
        connection.execute("SET enable_external_access=false")
        connection.execute("SET lock_configuration=true")

    def _build(self) -> tuple[duckdb.DuckDBPyConnection, frozenset[str]]:
        connection = duckdb.connect(":memory:")
        try:
            present = frozenset(name for name in self._paths if self.has_table(name))
            for name in sorted(present):
                literal = str(self._paths[name]).replace("'", "''")
                connection.execute(f"CREATE VIEW \"{name}\" AS SELECT * FROM read_parquet('{literal}')")
            self._lock_down(connection)
        except BaseException:
            connection.close()
            raise
        return connection, present

    def _current(self, tables: Sequence[str]) -> duckdb.DuckDBPyConnection:
        """The shared database, rebuilt when the files changed (checked at most once per interval)."""
        now = time.monotonic()
        with self._lock:
            stale = self._database is None or not self._registered.issuperset(tables)
            if stale or now - self._checked_at >= self._refresh_interval:
                self._checked_at = now
                signature = self._file_signature()
                if stale or signature != self._signature:
                    self._database, self._registered = self._build()
                    self._signature = signature
            if self._database is None:  # pragma: no cover - _build always sets it
                raise AssertionError("lake database not initialised")
            return self._database

    def _invalidate(self) -> None:
        """Drop the shared database so the next call opens the files again from scratch."""
        with self._lock:
            self._database = None

    def fetch(self, sql: str, params: Sequence[Any] = (), *, tables: Sequence[str]) -> list[Row]:
        missing = [name for name in tables if not self.has_table(name)]
        if missing:
            raise LakeUnavailableError(missing)
        if not sql.lstrip().lower().startswith(("select", "with")):
            raise ValueError("Only SELECT statements are allowed")
        _check_read_only(sql)
        for attempt in range(OPEN_ATTEMPTS):
            try:
                return self._run(sql, params, tables)
            except duckdb.IOException as exc:  # transient open failure (e.g. "Permission denied" in a burst)
                if attempt + 1 == OPEN_ATTEMPTS:
                    logger.warning("Lake read failed after %d attempts: %s", OPEN_ATTEMPTS, exc)
                    raise LakeUnavailableError(tables) from exc
                self._invalidate()
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        raise AssertionError("unreachable")  # pragma: no cover

    def _run(self, sql: str, params: Sequence[Any], tables: Sequence[str]) -> list[Row]:
        cursor = self._current(tables).cursor()
        try:
            result = cursor.execute(sql, list(params))
            columns = [column[0] for column in result.description]
            return [dict(zip(columns, record, strict=True)) for record in result.fetchall()]
        finally:
            cursor.close()
