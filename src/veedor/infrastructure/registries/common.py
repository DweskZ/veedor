"""Shared helpers: encoding detection, supplier RUC universe, SQL date parsing."""

from __future__ import annotations

import codecs
from pathlib import Path

import duckdb

_CHUNK = 1 << 22

# Accepts ISO timestamps/dates ("2001-05-28 00:00:00") and day-first dates ("28/05/2001").
PARSE_DATE_SQL = (
    "strftime(coalesce(try_strptime(left(trim({col}), 10), '%Y-%m-%d'),"
    " try_strptime(left(trim({col}), 10), '%d/%m/%Y')), '%Y-%m-%d')"
)


def parse_date_sql(column: str) -> str:
    """SQL expression turning a text column into an ISO `YYYY-MM-DD` string (NULL when unparsable)."""
    return PARSE_DATE_SQL.format(col=column)


def detect_encoding(path: Path) -> str:
    """Return `utf-8` when the whole file decodes as UTF-8, otherwise `latin-1`."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            try:
                decoder.decode(chunk)
            except UnicodeDecodeError:
                return "latin-1"
    try:
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return "latin-1"
    return "utf-8"


def load_ruc_universe(con: duckdb.DuckDBPyConnection, lake_dir: Path) -> int:
    """Create temp table `wanted_rucs` with every RUC in awards/tenderers. Returns its size."""
    sources = [lake_dir / "awards.parquet", lake_dir / "tenderers.parquet"]
    present = [p for p in sources if p.exists()]
    if not present:
        raise FileNotFoundError(f"Neither awards.parquet nor tenderers.parquet found in {lake_dir}")
    union = " UNION ".join(
        f"SELECT trim(supplier_ruc) AS ruc FROM read_parquet('{p}') WHERE supplier_ruc IS NOT NULL"
        for p in present
    )
    con.execute(f"CREATE OR REPLACE TEMP TABLE wanted_rucs AS {union}")
    return con.execute("SELECT count(*) FROM wanted_rucs").fetchone()[0]


def sql_str(value: object) -> str:
    """Quote a value as a SQL string literal."""
    return "'" + str(value).replace("'", "''") + "'"
