"""Reads in-scope processes (everything except catalogue purchases) from the Parquet lake."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path

import duckdb

from veedor.infrastructure.lake.connection import connect_lake, parquet_path, quote_literal
from veedor.use_cases.build_vectors import ProcessRecord

FETCH_SIZE = 10_000

_SELECT = """
WITH scope AS (
    SELECT ocid, year, buyer_ruc, buyer_name, method, award_total, main_cpc, main_cpc_description,
           description
    FROM processes
    WHERE method_group IS DISTINCT FROM 'catalogue'
      AND (description IS NOT NULL OR main_cpc_description IS NOT NULL)
      {ocid_filter}
    ORDER BY ocid
    {limit}
),
parties AS (
    SELECT ocid, supplier_ruc, supplier_name FROM tenderers WHERE ocid IN (SELECT ocid FROM scope)
    UNION
    SELECT ocid, supplier_ruc, supplier_name FROM awards WHERE ocid IN (SELECT ocid FROM scope)
),
agg AS (
    SELECT ocid, list(DISTINCT {{'ruc': supplier_ruc, 'name': supplier_name}}) AS parties
    FROM parties WHERE supplier_name IS NOT NULL GROUP BY ocid
)
SELECT s.*, a.parties, {winner_cols}
FROM scope s LEFT JOIN agg a USING (ocid) {winner_join}
ORDER BY s.ocid
"""


class LakeProcessSource:
    def __init__(self, lake_dir: Path, marts_dir: Path) -> None:
        self._lake_dir = lake_dir
        self._scores = parquet_path(marts_dir, "process_scores")

    def records(
        self, limit: int | None = None, ocids: Sequence[str] | None = None
    ) -> Iterator[ProcessRecord]:
        if not parquet_path(self._lake_dir, "processes").is_file():
            raise FileNotFoundError(
                f"{parquet_path(self._lake_dir, 'processes')} not found; build the lake first"
            )
        con = connect_lake(self._lake_dir)
        try:
            yield from self._stream(con, limit, ocids)
        finally:
            con.close()

    def _stream(
        self, con: duckdb.DuckDBPyConnection, limit: int | None, ocids: Sequence[str] | None
    ) -> Iterator[ProcessRecord]:
        for table in ("tenderers", "awards"):
            if not parquet_path(self._lake_dir, table).is_file():
                con.execute(
                    f'CREATE VIEW "{table}" AS SELECT NULL::VARCHAR AS ocid, NULL::VARCHAR AS supplier_ruc, '
                    "NULL::VARCHAR AS supplier_name WHERE false"
                )
        has_scores = self._scores.is_file()
        if has_scores:
            con.execute(
                f"CREATE VIEW scores AS SELECT ocid, winner_ruc, winner_name, winner_kind "
                f"FROM read_parquet({quote_literal(str(self._scores))})"
            )
        sql = _SELECT.format(
            ocid_filter="AND list_contains(?, ocid)" if ocids is not None else "",
            limit=f"LIMIT {int(limit)}" if limit else "",
            winner_cols="sc.winner_ruc, sc.winner_name, sc.winner_kind"
            if has_scores
            else "NULL AS winner_ruc, NULL AS winner_name, NULL AS winner_kind",
            winner_join="LEFT JOIN scores sc USING (ocid)" if has_scores else "",
        )
        cursor = con.execute(sql, [list(ocids)] if ocids is not None else [])
        columns = [c[0] for c in cursor.description]
        while rows := cursor.fetchmany(FETCH_SIZE):
            for row in rows:
                yield _record(dict(zip(columns, row, strict=True)))


def _record(row: dict) -> ProcessRecord:
    parties = tuple((p["ruc"], p["name"]) for p in (row["parties"] or ()))
    winner = (row["winner_ruc"], row["winner_name"], row["winner_kind"]) if row["winner_name"] else None
    return ProcessRecord(
        ocid=row["ocid"],
        year=row["year"],
        buyer_ruc=row["buyer_ruc"],
        buyer_name=row["buyer_name"],
        method=row["method"],
        award_total=row["award_total"],
        main_cpc=row["main_cpc"],
        cpc_description=row["main_cpc_description"],
        description=row["description"],
        parties=parties,
        winner=winner,
    )
