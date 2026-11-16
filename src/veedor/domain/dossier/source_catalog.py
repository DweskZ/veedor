"""Provenance of every dataset a dossier cites. One place, taken from docs/DATA_SOURCES.md."""

from __future__ import annotations

from veedor.domain.dossier.models import Source

RETRIEVED_AT = "2026-11-16"
NOT_DECLARED = "licencia no declarada por la fuente"
VEEDOR_LICENCE = "MIT (licencia del repositorio de Veedor)"

SERCOP_URL = "https://data.open-contracting.org/en/publication/110"
SERCOP_LICENCE = "CC BY 3.0 EC"
SERCOP_ORIGIN = "SERCOP, obtenido del Open Contracting Data Registry"


def sercop(dataset: str, record_id: str | None) -> Source:
    return Source(
        dataset=f"{dataset} ({SERCOP_ORIGIN})",
        licence=SERCOP_LICENCE,
        retrieved_at=RETRIEVED_AT,
        record_id=record_id,
        url=SERCOP_URL,
    )


def sri(dataset: str, record_id: str | None) -> Source:
    return Source(
        dataset=dataset,
        licence=NOT_DECLARED,
        retrieved_at=RETRIEVED_AT,
        record_id=record_id,
        url="https://www.sri.gob.ec/datasets",
    )


def supercias(dataset: str, record_id: str | None) -> Source:
    return Source(
        dataset=dataset,
        licence=NOT_DECLARED,
        retrieved_at=RETRIEVED_AT,
        record_id=record_id,
        url="https://appscvsmovil.supercias.gob.ec/ranking/",
    )


def veedor_indicators(record_id: str | None, retrieved_at: str | None) -> Source:
    return Source(
        dataset="Veedor: indicadores calculados sobre los datos anteriores",
        licence=VEEDOR_LICENCE,
        retrieved_at=retrieved_at,
        record_id=record_id,
    )
