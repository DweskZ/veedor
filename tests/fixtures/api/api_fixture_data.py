# ruff: noqa: E501
"""Tiny synthetic lake and marts for API and query tests (all entities are invented)."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

COMPANY_RUC = "1790012345001"  # third digit 9: company
COMPANY_NAME = "Constructora Ejemplo S.A."
NATURAL_RUC = "1712345678001"  # third digit 1: natural person
NATURAL_NAME = "Maria Ficticia Quispe"
BUYER_RUC = "1760001230001"  # third digit 6: public entity
BUYER_NAME = "GAD Municipal de Ejemplo"
OTHER_BUYER_RUC = "1760009990001"
HOSPITAL_NAME = "HOSPITAL DR. GUSTAVO DOMINGUEZ Z."  # a public entity named after a doctor
NATURAL_BUYER_RUC = "1712000000001"
NATURAL_BUYER_NAME = "Rosa Compradora Ejemplo"

OCID_COMPANY = "ocds-5wno2w-test-0001"
OCID_NATURAL = "ocds-5wno2w-test-0002"
OCID_DIRECT = "ocds-5wno2w-test-0003"
OCID_LAKE_ONLY = "ocds-5wno2w-test-0004"
CONTEXT_CODE = "GHOST_COMPANY_LISTED_LATER"
OCID_NORUC = "ocds-5wno2w-test-0006"
NORUC_NAME = "JOSE ANTONIO MENDEZ ROJAS"  # a person with no RUC in the data
ENTITY_NORUC_NAME = "CONSORCIO VIAL NORTE"  # legal entity with no RUC
CEDULA = "1710034065"  # valid check digit
DOCTOR_NAME = "Carlos Vega"
REVIEW_TOKEN = "test-review-token"
REVIEW_HEADERS = {"Authorization": f"Bearer {REVIEW_TOKEN}"}


def _write(path: Path, rows: list[dict], schema: pa.Schema | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)


def _tenderer(ocid, ruc, name):
    return {
        "ocid": ocid,
        "supplier_id": f"EC-RUC-{ruc}" if ruc else None,
        "supplier_ruc": ruc,
        "supplier_name": name,
    }


def _process(
    ocid,
    code,
    date,
    year,
    buyer_ruc,
    buyer_name,
    method,
    group,
    description,
    budget,
    tenderers,
    award,
    cpc="Servicios generales",
):
    return {
        "ocid": ocid,
        "process_code": code,
        "release_date": date,
        "year": year,
        "buyer_ruc": buyer_ruc,
        "buyer_name": buyer_name,
        "buyer_region": "Pichincha",
        "method": method,
        "method_group": group,
        "status": "complete",
        "description": description,
        "budget": budget,
        "n_tenderers": tenderers,
        "award_total": award,
        "main_cpc_description": cpc,
    }


def _score(
    ocid, risk, signals, award, year, buyer_ruc, buyer_name, method, w_ruc, w_name, w_kind, context=()
):
    return {
        "ocid": ocid, "risk_score": risk, "n_signals": len(signals), "signal_codes": signals,
        "anomaly_score": None, "award_total": award, "year": year, "buyer_ruc": buyer_ruc,
        "buyer_name": buyer_name, "method": method, "winner_ruc": w_ruc, "winner_name": w_name,
        "winner_kind": w_kind, "n_context_signals": len(context), "context_signal_codes": context,
    }  # fmt: skip


PROCESSES = [
    _process(OCID_COMPANY, "LICO-001", "2023-03-01T10:00:00-05:00", 2023, BUYER_RUC, BUYER_NAME, "Licitación",
             "competitive", "Construcción de aceras y bordillos", 1010.0, 1, 1000.0, cpc="Obras de aceras"),
    _process(OCID_NATURAL, "COT-002", "2023-06-15T09:00:00-05:00", 2023, BUYER_RUC, BUYER_NAME, "Cotización",
             "competitive", f"Servicio de mantenimiento a favor de {NATURAL_NAME} RUC {NATURAL_RUC}", 520.0, 2, 500.0),
    _process(OCID_DIRECT, "DIR-003", "2022-11-20T08:00:00-05:00", 2022, OTHER_BUYER_RUC, HOSPITAL_NAME,
             "Contratación directa", "direct", f"Insumos médicos suministrados por el Dr. {DOCTOR_NAME}", 200.0,
             None, 200.0),
    _process(OCID_LAKE_ONLY, "CAT-004", "2022-01-05T08:00:00-05:00", 2022, BUYER_RUC, BUYER_NAME,
             "Catálogo electrónico", "catalogue", "Papelería", 50.0, None, 50.0),
    _process(OCID_NORUC, "LICS-006", "2024-01-10T08:00:00-05:00", 2024, BUYER_RUC, BUYER_NAME, "Licitación",
             "competitive", f"Mantenimiento de vías con {NORUC_NAME}, cédula {CEDULA}", 95.0, 2, 90.0),
]  # fmt: skip

SCORES = [
    _score(OCID_COMPANY, 60.0, ["SINGLE_BIDDER", "LOW_SAVING"], 1000.0, 2023, BUYER_RUC, BUYER_NAME,
           "Licitación", COMPANY_RUC, COMPANY_NAME, "company", context=[CONTEXT_CODE]),
    _score(OCID_NATURAL, 40.0, ["SINGLE_BIDDER"], 500.0, 2023, BUYER_RUC, BUYER_NAME,
           "Cotización", NATURAL_RUC, NATURAL_NAME, "natural_person"),
    _score(OCID_DIRECT, 10.0, [], 200.0, 2022, OTHER_BUYER_RUC, HOSPITAL_NAME,
           "Contratación directa", COMPANY_RUC, COMPANY_NAME, "company"),
    _score("ocds-5wno2w-test-0005", 25.0, ["LOW_SAVING"], None, 2022, NATURAL_BUYER_RUC, NATURAL_BUYER_NAME,
           "Cotización", None, None, None),
    _score(OCID_NORUC, 30.0, ["SINGLE_BIDDER"], 90.0, 2024, BUYER_RUC, BUYER_NAME,
           "Licitación", None, NORUC_NAME, None),
]  # fmt: skip


def build_fixture_data(root: Path) -> tuple[Path, Path]:
    """Write the lake and marts under `root`; returns ``(lake_dir, marts_dir)``."""
    lake, marts = root / "lake", root / "marts"
    _write(lake / "processes.parquet", PROCESSES)
    _write(
        lake / "tenderers.parquet",
        [
            _tenderer(OCID_NATURAL, NATURAL_RUC, NATURAL_NAME),
            _tenderer(OCID_NATURAL, COMPANY_RUC, COMPANY_NAME),
            _tenderer(OCID_COMPANY, COMPANY_RUC, COMPANY_NAME),
            _tenderer(OCID_NORUC, None, NORUC_NAME),
            _tenderer(OCID_NORUC, None, ENTITY_NORUC_NAME),
        ],
    )
    _write(
        lake / "awards.parquet",
        [
            {
                "ocid": OCID_NATURAL,
                "award_id": "a-1",
                "award_date": "2023-06-30T00:00:00-05:00",
                "supplier_id": f"EC-RUC-{NATURAL_RUC}",
                "supplier_ruc": NATURAL_RUC,
                "supplier_name": NATURAL_NAME,
                "amount": 500.0,
            },
            {
                "ocid": OCID_NORUC,
                "award_id": "a-2",
                "award_date": "2024-02-01T00:00:00-05:00",
                "supplier_id": None,
                "supplier_ruc": None,
                "supplier_name": NORUC_NAME,
                "amount": 90.0,
            },
        ],
    )
    _write(
        lake / "suppliers_sri.parquet",
        [
            {"ruc": COMPANY_RUC, "legal_name": COMPANY_NAME, "status": "ACTIVO", "taxpayer_type": "SOCIEDADES",
             "activity_start_date": "2015-01-01", "province": "PICHINCHA"},
            {"ruc": NATURAL_RUC, "legal_name": NATURAL_NAME, "status": "ACTIVO", "taxpayer_type": "PERSONAS NATURALES",
             "activity_start_date": "2020-05-01", "province": "GUAYAS"},
        ],
    )  # fmt: skip
    _write(
        marts / "process_scores.parquet",
        SCORES,
        pa.schema(
            [
                ("ocid", pa.string()), ("risk_score", pa.float64()), ("n_signals", pa.int64()),
                ("signal_codes", pa.list_(pa.string())), ("anomaly_score", pa.float64()),
                ("award_total", pa.float64()), ("year", pa.int64()), ("buyer_ruc", pa.string()),
                ("buyer_name", pa.string()), ("method", pa.string()), ("winner_ruc", pa.string()),
                ("winner_name", pa.string()), ("winner_kind", pa.string()),
                ("n_context_signals", pa.int32()), ("context_signal_codes", pa.list_(pa.string())),
            ]
        ),
    )  # fmt: skip
    _write(
        marts / "process_signals.parquet",
        [
            {"ocid": OCID_COMPANY, "signal_code": "SINGLE_BIDDER", "value": 1.0, "threshold": 1.0,
             "evidence_json": json.dumps({"n_tenderers": 1}), "kind": "risk"},
            {"ocid": OCID_COMPANY, "signal_code": "LOW_SAVING", "value": 0.99, "threshold": 0.99,
             "evidence_json": json.dumps({"award_total": 1000.0, "budget": 1010.0}), "kind": "risk"},
            {"ocid": OCID_COMPANY, "signal_code": CONTEXT_CODE, "value": 1.0, "threshold": 1.0,
             "evidence_json": json.dumps({"listed_after_award": True}), "kind": "context"},
            {"ocid": OCID_NATURAL, "signal_code": "SINGLE_BIDDER", "value": 1.0, "threshold": 1.0,
             "evidence_json": json.dumps(
                 {"winner_ruc": NATURAL_RUC, "winner_name": NATURAL_NAME,
                  "note": f"Adjudicado a {NATURAL_NAME} ({NATURAL_RUC})"}
             ), "kind": "risk"},
            {"ocid": "ocds-5wno2w-test-0005", "signal_code": "LOW_SAVING", "value": 0.995, "threshold": 0.99,
             "evidence_json": "not json", "kind": "risk"},
        ],
    )  # fmt: skip
    _write(
        marts / "supplier_profiles.parquet",
        [
            {"ruc": COMPANY_RUC, "name": COMPANY_NAME, "kind": "company", "n_processes": 2, "n_wins": 2,
             "total_awarded": 1200.0, "first_award_date": "2022-11-20", "last_award_date": "2023-03-01",
             "n_buyers": 2, "top_buyer_ruc": BUYER_RUC, "top_buyer_share": 0.83, "single_bidder_wins": 1,
             "mean_risk_score": 35.0},
            {"ruc": NATURAL_RUC, "name": NATURAL_NAME, "kind": "natural_person", "n_processes": 1, "n_wins": 1,
             "total_awarded": 500.0, "first_award_date": "2023-06-30", "last_award_date": "2023-06-30",
             "n_buyers": 1, "top_buyer_ruc": BUYER_RUC, "top_buyer_share": 1.0, "single_bidder_wins": 1,
             "mean_risk_score": 40.0},
        ],
    )  # fmt: skip
    return lake, marts
