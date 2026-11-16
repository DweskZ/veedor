"""Tiny synthetic lake for the vector-search tests (every entity and person is invented)."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

COMPANY_RUC = "1790012345001"
COMPANY_NAME = "Constructora Ejemplo S.A."
NATURAL_RUC = "1712345678001"
NATURAL_NAME = "Maria Ficticia Quispe"
BUYER_RUC = "1760001230001"
BUYER_NAME = "GAD Municipal de Ejemplo"
OTHER_BUYER_RUC = "1760009990001"
OTHER_BUYER_NAME = "Hospital Ejemplo"
NATURAL_BUYER_RUC = "1712000000001"

CPC_ROADS = "Servicios de construcción de carreteras"
CPC_MEDICINE = "Medicamentos de uso humano"

OCID_ROAD_1 = "ocds-5wno2w-test-v001"
OCID_ROAD_2 = "ocds-5wno2w-test-v002"
OCID_ROAD_3 = "ocds-5wno2w-test-v003"
OCID_MED_1 = "ocds-5wno2w-test-v004"
OCID_MED_2 = "ocds-5wno2w-test-v005"
OCID_PERSON = "ocds-5wno2w-test-v006"  # description names the (natural person) winner
OCID_CEDULA = "ocds-5wno2w-test-v007"  # description carries a valid cédula
OCID_CATALOGUE = "ocds-5wno2w-test-v008"
OCID_NO_TEXT = "ocds-5wno2w-test-v009"
OCID_PERSON_NO_CPC = "ocds-5wno2w-test-v010"  # withheld description and no CPC text: nothing to embed
CEDULA = "1710034065"  # valid check digit


def _process(ocid, year, buyer, method_group, description, cpc, cpc_description, *, buyer_ruc=BUYER_RUC):
    return {
        "ocid": ocid, "year": year, "buyer_ruc": buyer_ruc, "buyer_name": buyer, "method": "Licitación",
        "method_group": method_group, "description": description, "award_total": 1000.0,
        "main_cpc": cpc, "main_cpc_description": cpc_description,
    }  # fmt: skip


PROCESSES = [
    _process(
        OCID_ROAD_1, 2022, BUYER_NAME, "competitive", "Asfaltado de la vía principal", "532100111", CPC_ROADS
    ),
    _process(
        OCID_ROAD_2, 2023, BUYER_NAME, "competitive", "Asfaltado de la vía secundaria", "532100111", CPC_ROADS
    ),
    _process(
        OCID_ROAD_3,
        2023,
        OTHER_BUYER_NAME,
        "direct",
        "Bacheo de calles",
        "532100999",
        CPC_ROADS,
        buyer_ruc=OTHER_BUYER_RUC,
    ),
    _process(
        OCID_MED_1,
        2023,
        OTHER_BUYER_NAME,
        "competitive",
        "Compra de antibióticos",
        "352100111",
        CPC_MEDICINE,
        buyer_ruc=OTHER_BUYER_RUC,
    ),
    _process(
        OCID_MED_2,
        2024,
        OTHER_BUYER_NAME,
        "direct",
        "Compra de analgésicos",
        "352100111",
        CPC_MEDICINE,
        buyer_ruc=OTHER_BUYER_RUC,
    ),
    _process(
        OCID_PERSON,
        2023,
        BUYER_NAME,
        "direct",
        f"Servicio prestado por {NATURAL_NAME} para el municipio",
        "532100111",
        CPC_ROADS,
    ),
    _process(
        OCID_CEDULA,
        2023,
        BUYER_NAME,
        "direct",
        f"Contrato con cédula {CEDULA} por mantenimiento",
        "532100111",
        CPC_ROADS,
    ),
    _process(OCID_CATALOGUE, 2023, BUYER_NAME, "catalogue", "Papelería", None, None),
    _process(OCID_NO_TEXT, 2023, BUYER_NAME, "no_tender_block", None, None, None),
    _process(OCID_PERSON_NO_CPC, 2023, BUYER_NAME, "direct", f"Servicio de {NATURAL_NAME}", None, None),
]


def _write(path: Path, rows: list[dict], schema: pa.Schema | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)


def _party(ocid: str, ruc: str, name: str) -> dict:
    return {"ocid": ocid, "supplier_id": f"EC-RUC-{ruc}", "supplier_ruc": ruc, "supplier_name": name}


def build_vector_lake(root: Path) -> tuple[Path, Path]:
    """Write lake and marts under `root`; returns ``(lake_dir, marts_dir)``."""
    lake, marts = root / "lake", root / "marts"
    _write(lake / "processes.parquet", PROCESSES)
    _write(
        lake / "tenderers.parquet",
        [
            _party(OCID_ROAD_1, COMPANY_RUC, COMPANY_NAME),
            _party(OCID_PERSON, NATURAL_RUC, NATURAL_NAME),
            _party(OCID_PERSON_NO_CPC, NATURAL_RUC, NATURAL_NAME),
        ],
    )
    _write(
        lake / "awards.parquet",
        [
            {"ocid": OCID_PERSON, "award_id": "a1", "award_date": None, "supplier_id": None,
             "supplier_ruc": NATURAL_RUC, "supplier_name": NATURAL_NAME, "amount": 10.0},
        ],
    )  # fmt: skip
    _write(
        marts / "process_scores.parquet",
        [
            {"ocid": OCID_PERSON, "winner_ruc": NATURAL_RUC, "winner_name": NATURAL_NAME,
             "winner_kind": "natural_person"},
            {"ocid": OCID_PERSON_NO_CPC, "winner_ruc": NATURAL_RUC, "winner_name": NATURAL_NAME,
             "winner_kind": "natural_person"},
            {"ocid": OCID_ROAD_1, "winner_ruc": COMPANY_RUC, "winner_name": COMPANY_NAME,
             "winner_kind": "company"},
        ],
    )  # fmt: skip
    return lake, marts
