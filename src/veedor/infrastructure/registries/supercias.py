"""Superintendencia de Compañías loaders: company directory and yearly financials."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from veedor.infrastructure.registries.common import detect_encoding, load_ruc_universe, sql_str

COMPANIES_TABLE = "companies_supercias"
FINANCIALS_TABLE = "company_financials"
COMPANY_FILE = "bi_compania.csv"
RANKING_FILE = "bi_ranking.csv"

# Source column -> output column (verified against the real files on 2026-11-16).
COMPANY_COLUMNS = {
    "expediente": "expediente",
    "ruc": "ruc",
    "nombre": "legal_name",
    "tipo": "company_type",
    "provincia": "province",
}
FINANCIAL_COLUMNS = {
    "anio": "year",
    "expediente": "expediente",
    "ingresos_ventas": "revenue",
    "ingresos_totales": "total_income",
    "activos": "assets",
    "patrimonio": "equity",
    "n_empleados": "employees",
}


@dataclass(frozen=True)
class SuperciasResult:
    companies: int
    financials: int
    wanted_rucs: int
    matched_rucs: int

    @property
    def match_rate(self) -> float:
        return self.matched_rucs / self.wanted_rucs if self.wanted_rucs else 0.0


def _read_csv(path: Path, columns: dict[str, str]) -> str:
    """`read_csv` call that fails loudly when an expected column is missing."""
    encoding = detect_encoding(path)
    with path.open(encoding=encoding, newline="") as handle:
        header = handle.readline().strip().split(",")
    missing = set(columns) - set(header)
    if missing:
        raise ValueError(f"{path.name}: unexpected header, missing columns {sorted(missing)}")
    return (
        f"read_csv({sql_str(path)}, header=true, all_varchar=true, encoding={sql_str(encoding)}, "
        "null_padding=true, strict_mode=false)"
    )


def _num(column: str) -> str:
    return f"try_cast(nullif(trim({column}), '') AS DOUBLE)"


def build_companies(raw_dir: Path, lake_dir: Path, con: duckdb.DuckDBPyConnection) -> int:
    source = _read_csv(raw_dir / COMPANY_FILE, COMPANY_COLUMNS)
    out = lake_dir / f"{COMPANIES_TABLE}.parquet"
    con.execute(
        f"COPY (SELECT try_cast(trim(expediente) AS BIGINT) AS expediente, nullif(trim(ruc), '') AS ruc, "
        f"nullif(trim(nombre), '') AS legal_name, nullif(trim(tipo), '') AS company_type, "
        f"nullif(trim(provincia), '') AS province FROM {source} ORDER BY expediente) "
        f"TO {sql_str(out)} (FORMAT parquet, COMPRESSION zstd)"
    )
    return con.execute(f"SELECT count(*) FROM read_parquet({sql_str(out)})").fetchone()[0]


def build_financials(raw_dir: Path, lake_dir: Path, con: duckdb.DuckDBPyConnection) -> int:
    """Join the ranking file to the directory (via `expediente`) to attach RUCs."""
    source = _read_csv(raw_dir / RANKING_FILE, FINANCIAL_COLUMNS)
    companies = lake_dir / f"{COMPANIES_TABLE}.parquet"
    out = lake_dir / f"{FINANCIALS_TABLE}.parquet"
    con.execute(
        f"COPY (SELECT c.ruc, try_cast(r.anio AS INTEGER) AS year, r.expediente_n AS expediente, "
        f"r.revenue, r.total_income, r.assets, r.equity, r.employees FROM ("
        f"SELECT try_cast(trim(expediente) AS BIGINT) AS expediente_n, anio, "
        f"{_num('ingresos_ventas')} AS revenue, {_num('ingresos_totales')} AS total_income, "
        f"{_num('activos')} AS assets, {_num('patrimonio')} AS equity, {_num('n_empleados')} AS employees "
        f"FROM {source}) r JOIN read_parquet({sql_str(companies)}) c ON c.expediente = r.expediente_n "
        f"WHERE c.ruc IS NOT NULL ORDER BY c.ruc, year) TO {sql_str(out)} (FORMAT parquet, COMPRESSION zstd)"
    )
    return con.execute(f"SELECT count(*) FROM read_parquet({sql_str(out)})").fetchone()[0]


def build_supercias(raw_dir: Path, lake_dir: Path) -> SuperciasResult:
    lake_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    wanted = load_ruc_universe(con, lake_dir)
    companies = build_companies(raw_dir, lake_dir, con)
    financials = build_financials(raw_dir, lake_dir, con) if (raw_dir / RANKING_FILE).exists() else 0
    matched = con.execute(
        f"SELECT count(DISTINCT w.ruc) FROM wanted_rucs w JOIN "
        f"read_parquet({sql_str(lake_dir / (COMPANIES_TABLE + '.parquet'))}) c ON c.ruc = w.ruc"
    ).fetchone()[0]
    return SuperciasResult(companies, financials, wanted, matched)
