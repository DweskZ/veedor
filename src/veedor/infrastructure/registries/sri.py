"""SRI loaders: RUC registry (per-province CSV zips) and the ghost-company catalogue."""

from __future__ import annotations

import csv
import io
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from veedor.infrastructure.registries.common import (
    detect_encoding,
    load_ruc_universe,
    parse_date_sql,
    sql_str,
)

# Source column -> output column. Verified against the real files on 2026-11-16.
RUC_COLUMNS = {
    "NUMERO_RUC": "ruc",
    "RAZON_SOCIAL": "legal_name",
    "ESTADO_CONTRIBUYENTE": "status",
    "TIPO_CONTRIBUYENTE": "taxpayer_type",
    "FECHA_INICIO_ACTIVIDADES": "activity_start_date",
    "FECHA_SUSPENSION_DEFINITIVA": "suspension_date",
    "FECHA_REINICIO_ACTIVIDADES": "restart_date",
    "CODIGO_CIIU": "ciiu_code",
    "ACTIVIDAD_ECONOMICA": "activity",
    "DESCRIPCION_PROVINCIA_EST": "province",
    "NUMERO_ESTABLECIMIENTO": "establishment_number",
}
_DATE_FIELDS = {"FECHA_INICIO_ACTIVIDADES", "FECHA_SUSPENSION_DEFINITIVA", "FECHA_REINICIO_ACTIVIDADES"}

SUPPLIERS_TABLE = "suppliers_sri"
GHOST_TABLE = "ghost_companies"
GHOST_SOURCE_NAME = "SRI_Catastro_Empresas_Fantasmas.csv"

GHOST_COLUMNS = {
    "NUMERO_RUC": "ruc",
    "RAZON_SOCIAL": "legal_name",
    "RESOLUCION_CALIFICACION": "resolution",
    "FECHA_NOTIFICACION_RESOLUCION": "notification_date",
    "TIPO_CONTRIBUYENTE": "taxpayer_type",
    "DETALLE_CALIFICACION": "qualification_detail",
    "ESTADO_RUC": "ruc_status",
    "ESTADO_IMPUGNACIÓN": "challenge_state",
}
EXCEL_EPOCH = date(1899, 12, 30)


@dataclass(frozen=True)
class SuppliersResult:
    rows: int
    wanted_rucs: int
    matched_rucs: int
    files: int

    @property
    def match_rate(self) -> float:
        return self.matched_rucs / self.wanted_rucs if self.wanted_rucs else 0.0


def _select_sql(csv_path: Path, encoding: str, source_file: str) -> str:
    exprs = []
    for src, out in RUC_COLUMNS.items():
        col = f'"{src}"'
        expr = parse_date_sql(col) if src in _DATE_FIELDS else f"nullif(trim({col}), '')"
        exprs.append(f"{expr} AS {out}")
    return (
        f"SELECT {', '.join(exprs)}, {sql_str(source_file)} AS source_file "
        f"FROM read_csv({sql_str(csv_path)}, delim='|', header=true, all_varchar=true, "
        "quote='\"', escape='\"', strict_mode=false, "
        f"encoding={sql_str(encoding)}, null_padding=true) "
        f'WHERE trim("NUMERO_RUC") IN (SELECT ruc FROM wanted_rucs)'
    )


def check_header(csv_path: Path, encoding: str) -> None:
    with csv_path.open(encoding=encoding, newline="") as handle:
        header = handle.readline().rstrip("\r\n").split("|")
    missing = set(RUC_COLUMNS) - set(header)
    if missing:
        raise ValueError(f"{csv_path.name}: unexpected header, missing columns {sorted(missing)}")


def build_suppliers_sri(raw_dir: Path, lake_dir: Path) -> SuppliersResult:
    """Build suppliers_sri.parquet from SRI_RUC_*.zip, keeping only RUCs present in the lake."""
    zips = sorted(raw_dir.glob("SRI_RUC_*.zip"))
    if not zips:
        raise FileNotFoundError(f"No SRI_RUC_*.zip in {raw_dir}; run `veedor registries download` first.")
    con = duckdb.connect()
    wanted = load_ruc_universe(con, lake_dir)
    first = True
    with tempfile.TemporaryDirectory(prefix="veedor_sri_") as tmp:
        for archive in zips:
            for csv_path in _extract_csvs(archive, Path(tmp)):
                encoding = detect_encoding(csv_path)
                check_header(csv_path, encoding)
                select = _select_sql(csv_path, encoding, archive.name)
                con.execute(("CREATE TEMP TABLE sri_raw AS " if first else "INSERT INTO sri_raw ") + select)
                first = False
                csv_path.unlink()
    lake_dir.mkdir(parents=True, exist_ok=True)
    out = lake_dir / f"{SUPPLIERS_TABLE}.parquet"
    # One row per RUC: the lowest establishment number (the head establishment) wins.
    con.execute(
        f"COPY (SELECT * EXCLUDE (establishment_number) FROM sri_raw "
        f"QUALIFY row_number() OVER (PARTITION BY ruc ORDER BY try_cast(establishment_number AS INTEGER), "
        f"source_file) = 1 ORDER BY ruc) TO {sql_str(out)} (FORMAT parquet, COMPRESSION zstd)"
    )
    rows = con.execute(f"SELECT count(*) FROM read_parquet({sql_str(out)})").fetchone()[0]
    return SuppliersResult(rows=rows, wanted_rucs=wanted, matched_rucs=rows, files=len(zips))


def _extract_csvs(archive: Path, dest: Path) -> list[Path]:
    paths = []
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if member.filename.lower().endswith(".csv"):
                target = dest / f"{archive.stem}__{Path(member.filename).name}"
                with bundle.open(member) as src, target.open("wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
                paths.append(target)
    return paths


def excel_serial_to_iso(value: str | None) -> str | None:
    """Convert an Excel day serial (e.g. `43003`) to `YYYY-MM-DD`; None when empty or not numeric."""
    text = (value or "").strip()
    if not text.isdigit():
        return None
    return (EXCEL_EPOCH + timedelta(days=int(text))).isoformat()


def read_ghost_rows(path: Path, encoding: str) -> list[dict[str, str]]:
    """Parse the ghost catalogue. Some records are wrapped in an extra pair of quotes: re-parse them."""
    records = []
    with path.open(encoding=encoding, newline="") as handle:
        rows = csv.reader(handle, delimiter="|")
        header = [h.strip() for h in next(rows)]
        for row in rows:
            if not row:
                continue
            if len(row) == 1:
                row = next(csv.reader(io.StringIO(row[0], newline=""), delimiter="|"), [])
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            records.append(dict(zip(header, (cell.strip() for cell in row), strict=False)))
    return records


def build_ghost_companies(raw_dir: Path, lake_dir: Path) -> int:
    """Build ghost_companies.parquet from the SRI catalogue. Returns the row count."""
    path = raw_dir / GHOST_SOURCE_NAME
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run `veedor registries download` first.")
    records = read_ghost_rows(path, detect_encoding(path))
    columns: dict[str, list[str | None]] = {out: [] for out in GHOST_COLUMNS.values()}
    for record in records:
        if not record.get("NUMERO_RUC"):
            continue
        for src, out in GHOST_COLUMNS.items():
            value = record.get(src) or None
            columns[out].append(excel_serial_to_iso(value) if out == "notification_date" else value)
    n = len(columns["ruc"])
    columns["publication_date"] = [None] * n  # not provided by the source
    columns["source_file"] = [GHOST_SOURCE_NAME] * n
    lake_dir.mkdir(parents=True, exist_ok=True)
    table = pa.table({k: pa.array(v, type=pa.string()) for k, v in columns.items()})
    pq.write_table(table, lake_dir / f"{GHOST_TABLE}.parquet", compression="zstd")
    return n
