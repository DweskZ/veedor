"""Ports and errors shared by the read-side use cases."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

Row = dict[str, Any]


class LakeUnavailableError(Exception):
    """A Parquet table needed by a query does not exist (yet)."""

    def __init__(self, tables: Sequence[str]) -> None:
        self.tables = tuple(tables)
        super().__init__(f"Required data tables are not available: {', '.join(self.tables)}")


class NotFoundError(Exception):
    """The requested entity does not exist in the data."""

    def __init__(self, kind: str, key: str) -> None:
        self.kind = kind
        self.key = key
        super().__init__(f"{kind} {key!r} not found")


class LakePort(Protocol):
    """Read-only, parameterised access to lake and mart tables.

    SQL refers to tables by their logical name (``process_scores``, ``processes``...).
    """

    def fetch(self, sql: str, params: Sequence[Any] = (), *, tables: Sequence[str]) -> list[Row]: ...

    def has_table(self, name: str) -> bool: ...

    def availability(self) -> dict[str, bool]: ...


class DossierUnavailableError(Exception):
    """The dossier builder is not installed or could not run."""
