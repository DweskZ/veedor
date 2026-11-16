"""Read-only local tools over the Parquet lake: pair awards, reference dates, buyer-name index.

The connection is in memory with external access locked to the lake folder, like the dossier's evidence
reader. Real RUCs only come from the pack of a company or public entity; the tools refuse anything
else before running a query.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import duckdb

from veedor.domain.investigation.entity_match import build_key_index

_RUC = re.compile(r"^[0-9]{13}$")
_REFERENCE_DAY = "substr(coalesce(first_award_date, date_signed, tender_start, release_date), 1, 10)"


class LakeTools:
    def __init__(self, lake_dir: Path, marts_dir: Path | None = None) -> None:
        self.lake_dir = lake_dir
        self.marts_dir = marts_dir or lake_dir.parent / "marts"
        self._con: duckdb.DuckDBPyConnection | None = None
        self._key_index: dict[str, frozenset[str]] | None = None

    # connection ----------------------------------------------------------------------------
    def _connection(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            con = duckdb.connect(":memory:")
            for table in ("processes", "awards"):
                path = self.lake_dir / f"{table}.parquet"
                if not path.is_file():
                    con.close()
                    raise FileNotFoundError(table)
                escaped = str(path).replace("'", "''")
                con.execute(f"CREATE VIEW \"{table}\" AS SELECT * FROM read_parquet('{escaped}')")
            allowed = "'" + str(self.lake_dir.resolve()).replace("'", "''") + "'"
            con.execute(f"SET allowed_directories=[{allowed}]")
            con.execute("SET enable_external_access=false")
            con.execute("SET lock_configuration=true")
            self._con = con
        return self._con

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    # tools ---------------------------------------------------------------------------------
    def pair_awards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Awards of this buyer to this supplier at any date, not counting the given process."""
        buyer, supplier, ocid = (arguments.get(k) for k in ("buyer_ruc", "supplier_ruc", "ocid"))
        if not (isinstance(buyer, str) and isinstance(supplier, str) and _RUC.match(buyer)
                and _RUC.match(supplier) and isinstance(ocid, str)):  # fmt: skip
            raise ValueError("invalid arguments")
        row = (
            self._connection()
            .execute(
                "SELECT count(*) AS n, count(a.amount) AS n_amount, sum(a.amount) AS total "
                "FROM awards a JOIN processes p USING (ocid) "
                "WHERE a.supplier_ruc = ? AND p.buyer_ruc = ? AND a.ocid <> ?",
                [supplier, buyer, ocid],
            )
            .fetchone()
        )
        return {"n_other_awards": int(row[0]), "n_with_amount": int(row[1]), "total_other_amount": row[2]}

    def reference_days(self, ocids: list[str]) -> dict[str, str]:
        """ISO reference day per ocid (first award, signature, tender start, publication)."""
        if not ocids:
            return {}
        rows = (
            self._connection()
            .execute(f"SELECT ocid, {_REFERENCE_DAY} FROM processes WHERE list_contains(?, ocid)", [ocids])
            .fetchall()
        )
        return {ocid: day for ocid, day in rows if day}

    def embedding_basis(self, ocids: list[str]) -> dict[str, str]:
        """What each process's embedding was made of: ``description`` or ``classification`` (CPC only)."""
        from veedor.infrastructure.vectors.source import LakeProcessSource
        from veedor.use_cases.build_vectors import STATUS_DESCRIPTION_ONLY, STATUS_FULL, compose_text

        out: dict[str, str] = {}
        for record in LakeProcessSource(self.lake_dir, self.marts_dir).records(ocids=ocids):
            _, status = compose_text(record)
            out[record.ocid] = (
                "description" if status in (STATUS_FULL, STATUS_DESCRIPTION_ONLY) else "classification"
            )
        return out

    def buyer_key_index(self) -> dict[str, frozenset[str]]:
        """Canonical entity key -> distinct buyer RUCs that share it (cached for the session)."""
        if self._key_index is None:
            rows = (
                self._connection()
                .execute("SELECT DISTINCT buyer_ruc, buyer_name FROM processes WHERE buyer_ruc IS NOT NULL")
                .fetchall()
            )
            self._key_index = build_key_index((ruc, name) for ruc, name in rows if name)
        return self._key_index
