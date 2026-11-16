"""Tiny synthetic Parquet lakes for the marts builder tests (no network, no real data)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from veedor.infrastructure.ocds.flatten import AWARD_SCHEMA, PROCESS_SCHEMA, TENDERER_SCHEMA

BASE_DAY = date(2020, 3, 1)

PROCESS_DEFAULTS: dict[str, Any] = {
    "year": 2020,
    "buyer_ruc": "1760000000001",
    "buyer_name": "Entidad Sintetica",
    "method": "Menor Cuantía",
    "method_group": "competitive",
    "budget": 1000.0,
    "award_total": 900.0,
    "n_tenderers": 3,
    "n_tenderers_listed": 3,
    "n_bids": 3,
    "n_enquiries": 0,
    "n_awards": 1,
    "has_tender_block": True,
    "main_cpc": "12345678",
}


def stamp(day: date, hour: int = 10) -> str:
    return f"{day.isoformat()}T{hour:02d}:00:00-05:00"


def process(ocid: str, **fields: Any) -> dict[str, Any]:
    row = {**PROCESS_DEFAULTS, "ocid": ocid, "process_code": ocid, **fields}
    row.setdefault("first_award_date", stamp(BASE_DAY + timedelta(days=30)))
    return row


def award(ocid: str, ruc: str, amount: float | None = 900.0, award_date: str | None = None) -> dict[str, Any]:
    return {
        "ocid": ocid,
        "award_id": f"{ocid}-a",
        "award_date": award_date or stamp(BASE_DAY + timedelta(days=30)),
        "supplier_id": f"EC-RUC-{ruc}",
        "supplier_ruc": ruc,
        "supplier_name": f"Proveedor {ruc}",
        "amount": amount,
    }


def tenderer(ocid: str, ruc: str) -> dict[str, Any]:
    return {
        "ocid": ocid,
        "supplier_id": f"EC-RUC-{ruc}",
        "supplier_ruc": ruc,
        "supplier_name": f"Proveedor {ruc}",
    }


def write_table(lake: Path, name: str, rows: list[dict[str, Any]], schema: pa.Schema | None = None) -> None:
    lake.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=schema) if schema else pa.Table.from_pylist(rows)
    pq.write_table(table, lake / f"{name}.parquet")


def write_lake(
    lake: Path,
    processes: list[dict[str, Any]],
    awards: list[dict[str, Any]] | None = None,
    tenderers: list[dict[str, Any]] | None = None,
) -> None:
    """Write the three core tables; missing keys in process rows become null."""
    full = [{name: row.get(name) for name in PROCESS_SCHEMA.names} for row in processes]
    write_table(lake, "processes", full, PROCESS_SCHEMA)
    write_table(lake, "awards", awards or [], AWARD_SCHEMA)
    write_table(lake, "tenderers", tenderers or [], TENDERER_SCHEMA)
