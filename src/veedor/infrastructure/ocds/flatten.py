"""Flatten the SERCOP OCDS bulk file (gzip JSON Lines, one compiled release per line)
into three Parquet tables: processes, tenderers and awards.

The flattening is deliberately explicit: every output column is derived from a named
OCDS field, so each downstream indicator can be traced back to the source record.
"""

from __future__ import annotations

import gzip
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import orjson
import pyarrow as pa
import pyarrow.parquet as pq

RUC_RE = re.compile(r"EC-RUC-(\d{13})")

CATALOGUE_PREFIX = "Catálogo electrónico"

# Procedures where suppliers compete for the award.
COMPETITIVE_METHODS = frozenset(
    {
        "Subasta Inversa Electrónica",
        "Menor Cuantía",
        "Cotización",
        "Licitación",
        "Licitación de Seguros",
        "Lista corta",
        "Concurso publico",
        "Concurso público",
        "Contratacion directa",  # consultancy "direct contracting": kept separate below
    }
)
# Procedures awarded without open competition by design.
DIRECT_METHODS = frozenset(
    {
        "Contratacion directa",
        "Bienes y Servicios únicos",
        "Comunicación Social – Contratación Directa",
        "Contratos entre Entidades Públicas o sus subsidiarias",
        "Repuestos o Accesorios",
        "Obra artística, científica o literaria",
        "Asesoría y Patrocinio Jurídico",
        "Transporte de correo interno o internacional",
        "Contrataciones con empresas públicas internacionales",
    }
)

PROCESS_SCHEMA = pa.schema(
    [
        ("ocid", pa.string()),
        ("process_code", pa.string()),
        ("release_date", pa.string()),
        ("year", pa.int16()),
        ("buyer_id", pa.string()),
        ("buyer_ruc", pa.string()),
        ("buyer_name", pa.string()),
        ("buyer_region", pa.string()),
        ("buyer_locality", pa.string()),
        ("method", pa.string()),
        ("method_group", pa.string()),
        ("category", pa.string()),
        ("status", pa.string()),
        ("description", pa.string()),
        ("budget", pa.float64()),
        ("budget_source", pa.string()),
        ("tender_start", pa.string()),
        ("tender_end", pa.string()),
        ("enquiry_start", pa.string()),
        ("enquiry_end", pa.string()),
        ("award_period_start", pa.string()),
        ("award_period_end", pa.string()),
        ("n_tenderers", pa.int32()),
        ("n_tenderers_listed", pa.int32()),
        ("n_bids", pa.int32()),
        ("n_enquiries", pa.int32()),
        ("n_awards", pa.int32()),
        ("award_total", pa.float64()),
        ("first_award_date", pa.string()),
        ("date_signed", pa.string()),
        ("main_cpc", pa.string()),
        ("main_cpc_description", pa.string()),
        ("has_tender_block", pa.bool_()),
    ]
)

TENDERER_SCHEMA = pa.schema(
    [
        ("ocid", pa.string()),
        ("supplier_id", pa.string()),
        ("supplier_ruc", pa.string()),
        ("supplier_name", pa.string()),
    ]
)

AWARD_SCHEMA = pa.schema(
    [
        ("ocid", pa.string()),
        ("award_id", pa.string()),
        ("award_date", pa.string()),
        ("supplier_id", pa.string()),
        ("supplier_ruc", pa.string()),
        ("supplier_name", pa.string()),
        ("amount", pa.float64()),
    ]
)


def extract_ruc(party_id: Any) -> str | None:
    """Return the 13-digit RUC embedded in an OCDS party id, if any."""
    if not isinstance(party_id, str):
        return None
    match = RUC_RE.search(party_id)
    return match.group(1) if match else None


def method_group(method: str | None, has_tender: bool) -> str:
    if not has_tender:
        return "no_tender_block"
    if not method:
        return "unknown"
    if method.startswith(CATALOGUE_PREFIX):
        return "catalogue"
    if method in DIRECT_METHODS:
        return "direct"
    if method in COMPETITIVE_METHODS:
        return "competitive"
    return "other"


def _amount(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("amount")
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return float(raw)
    return None


def _budget(release: dict[str, Any], tender: dict[str, Any]) -> tuple[float | None, str | None]:
    """Budget in priority order: tender.value, sum of lot values, planning.budget.amount."""
    value = _amount(tender.get("value"))
    if value is not None:
        return value, "tender.value"
    lots = tender.get("lots") or []
    lot_amounts = (_amount(lot.get("value")) for lot in lots if isinstance(lot, dict))
    lot_values = [v for v in lot_amounts if v is not None]
    if lot_values:
        return float(sum(lot_values)), "tender.lots"
    planning_budget = ((release.get("planning") or {}).get("budget") or {}).get("amount")
    value = _amount(planning_budget)
    if value is not None:
        return value, "planning.budget"
    return None, None


def _text(value: Any, limit: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    return value[:limit] if limit else value


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def flatten(release: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Turn one OCDS release into a process row plus tenderer and award rows."""
    ocid = release.get("ocid")
    tender = release.get("tender") or {}
    has_tender = bool(tender)
    buyer = release.get("buyer") or {}
    buyer_id = buyer.get("id")

    buyer_region = buyer_locality = None
    for party in release.get("parties") or []:
        if isinstance(party, dict) and party.get("id") == buyer_id:
            address = party.get("address") or {}
            buyer_region = _text(address.get("region"))
            buyer_locality = _text(address.get("locality"))
            break

    method = _text(tender.get("procurementMethodDetails")) or _text(tender.get("procurementMethod"))
    budget, budget_source = _budget(release, tender)

    tender_period = tender.get("tenderPeriod") or {}
    enquiry_period = tender.get("enquiryPeriod") or {}
    award_period = tender.get("awardPeriod") or {}

    tenderer_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for tenderer in tender.get("tenderers") or []:
        if not isinstance(tenderer, dict):
            continue
        supplier_id = tenderer.get("id")
        key = supplier_id or tenderer.get("name")
        if not key or key in seen:
            continue
        seen.add(key)
        tenderer_rows.append(
            {
                "ocid": ocid,
                "supplier_id": supplier_id,
                "supplier_ruc": extract_ruc(supplier_id),
                "supplier_name": _text(tenderer.get("name")),
            }
        )

    award_rows: list[dict[str, Any]] = []
    award_total = 0.0
    award_seen = False
    award_dates: list[str] = []
    for award in release.get("awards") or []:
        if not isinstance(award, dict):
            continue
        amount = _amount(award.get("value"))
        if amount is not None:
            award_total += amount
            award_seen = True
        award_date = _text(award.get("date"))
        if award_date:
            award_dates.append(award_date)
        suppliers = [s for s in (award.get("suppliers") or []) if isinstance(s, dict)]
        for supplier in suppliers or [{}]:
            supplier_id = supplier.get("id")
            award_rows.append(
                {
                    "ocid": ocid,
                    "award_id": _text(str(award.get("id"))) if award.get("id") is not None else None,
                    "award_date": award_date,
                    "supplier_id": supplier_id,
                    "supplier_ruc": extract_ruc(supplier_id),
                    "supplier_name": _text(supplier.get("name")),
                    # When an award lists several suppliers the amount is not split in the source.
                    "amount": amount if len(suppliers) <= 1 else None,
                }
            )

    date_signed = None
    for contract in release.get("contracts") or []:
        if isinstance(contract, dict) and _text(contract.get("dateSigned")):
            date_signed = _text(contract.get("dateSigned"))
            break

    main_cpc = main_cpc_description = None
    for item in tender.get("items") or []:
        if isinstance(item, dict):
            classification = item.get("classification") or {}
            main_cpc = _text(str(classification.get("id"))) if classification.get("id") is not None else None
            main_cpc_description = _text(classification.get("description"), 300)
            break

    release_date = _text(release.get("date"))
    year_source = _text(tender_period.get("startDate")) or release_date
    year = int(year_source[:4]) if year_source and year_source[:4].isdigit() else None

    bids = (release.get("bids") or {}).get("details") or []

    process_row = {
        "ocid": ocid,
        "process_code": _text(tender.get("id")) or _text(tender.get("title")),
        "release_date": release_date,
        "year": year,
        "buyer_id": buyer_id,
        "buyer_ruc": extract_ruc(buyer_id),
        "buyer_name": _text(buyer.get("name")),
        "buyer_region": buyer_region,
        "buyer_locality": buyer_locality,
        "method": method,
        "method_group": method_group(method, has_tender),
        "category": _text(tender.get("mainProcurementCategory")),
        "status": _text(tender.get("status")),
        "description": _text(tender.get("description"), 600),
        "budget": budget,
        "budget_source": budget_source,
        "tender_start": _text(tender_period.get("startDate")),
        "tender_end": _text(tender_period.get("endDate")),
        "enquiry_start": _text(enquiry_period.get("startDate")),
        "enquiry_end": _text(enquiry_period.get("endDate")),
        "award_period_start": _text(award_period.get("startDate")),
        "award_period_end": _text(award_period.get("endDate")),
        "n_tenderers": _int(tender.get("numberOfTenderers")),
        "n_tenderers_listed": len(tenderer_rows),
        "n_bids": len(bids) if isinstance(bids, list) else 0,
        "n_enquiries": len(tender.get("enquiries") or []),
        "n_awards": len(release.get("awards") or []),
        "award_total": award_total if award_seen else None,
        "first_award_date": min(award_dates) if award_dates else None,
        "date_signed": date_signed,
        "main_cpc": main_cpc,
        "main_cpc_description": main_cpc_description,
        "has_tender_block": has_tender,
    }
    return process_row, tenderer_rows, award_rows


def iter_releases(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rb") as handle:
        for line in handle:
            if line.strip():
                yield orjson.loads(line)


class BatchWriter:
    def __init__(self, path: Path, schema: pa.Schema, batch_size: int) -> None:
        self._writer = pq.ParquetWriter(path, schema, compression="zstd")
        self._schema = schema
        self._batch_size = batch_size
        self._rows: list[dict[str, Any]] = []
        self.count = 0

    def extend(self, rows: list[dict[str, Any]]) -> None:
        self._rows.extend(rows)
        if len(self._rows) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        if self._rows:
            self._writer.write_table(pa.Table.from_pylist(self._rows, schema=self._schema))
            self.count += len(self._rows)
            self._rows = []

    def close(self) -> None:
        self.flush()
        self._writer.close()


def build_lake(
    source: Path,
    lake_dir: Path,
    batch_size: int = 50_000,
    limit: int | None = None,
    *,
    with_texts: bool = False,
    texts_dir: Path | None = None,
) -> dict[str, int]:
    """Stream the bulk file once and write processes/tenderers/awards Parquet files.

    With `with_texts` the same pass also writes `process_texts.parquet` (see `ocds.texts`) into
    `texts_dir` (default: a ``texts`` folder next to the lake folder, never inside it)."""
    from veedor.infrastructure.ocds.texts import TextSink  # texts.py imports this module

    lake_dir.mkdir(parents=True, exist_ok=True)
    processes = BatchWriter(lake_dir / "processes.parquet", PROCESS_SCHEMA, batch_size)
    tenderers = BatchWriter(lake_dir / "tenderers.parquet", TENDERER_SCHEMA, batch_size)
    awards = BatchWriter(lake_dir / "awards.parquet", AWARD_SCHEMA, batch_size)
    texts = TextSink(texts_dir or lake_dir.parent / "texts", batch_size) if with_texts else None
    try:
        for index, release in enumerate(iter_releases(source)):
            if limit is not None and index >= limit:
                break
            process_row, tenderer_rows, award_rows = flatten(release)
            processes.extend([process_row])
            tenderers.extend(tenderer_rows)
            awards.extend(award_rows)
            if texts is not None:
                texts.add(release)
    except BaseException:
        if texts is not None:
            texts.abort()
        raise
    finally:
        processes.close()
        tenderers.close()
        awards.close()
    counts = {"processes": processes.count, "tenderers": tenderers.count, "awards": awards.count}
    if texts is not None:
        counts["texts"] = texts.close()["rows"]
    return counts


if __name__ == "__main__":
    import sys

    counts = build_lake(Path(sys.argv[1]), Path(sys.argv[2]))
    print(counts)
