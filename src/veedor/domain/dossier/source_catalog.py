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


# --- sources of the investigation (stage 2) ---------------------------------------------------
# Licences are what the sources declare. Where the source declares none the text says so; nothing is
# assumed. Live lookups go through EcuDataMCP, which is named so a reader can reproduce the query.

MCP_ORIGIN = "consulta en línea mediante EcuDataMCP"
SRI_LIVE_URL = "https://srienlinea.sri.gob.ec/facturacion-internet/consultas/publico/ruc-datos2.jspa"
CONTRALORIA_URL = "https://www.contraloria.gob.ec"
SUPERCIAS_URL = "https://appscvsmovil.supercias.gob.ec/ranking/"


def _live(dataset: str, licence_note: str, url: str | None, record_id: str | None, note: str) -> Source:
    return Source(
        dataset=dataset,
        licence=licence_note,
        retrieved_at=None,  # set by the investigation to the day of the query
        record_id=record_id,
        url=url,
        note=note,
    )


def supercias_company_live(record_id: str | None) -> Source:
    return _live(
        f"Superintendencia de Compañías: directorio de compañías ({MCP_ORIGIN})",
        NOT_DECLARED,
        SUPERCIAS_URL,
        record_id,
        "Se conserva solo la fecha de constitución, el capital suscrito, la situación legal y el último "
        "balance; no se almacenan nombres de personas.",
    )


def supercias_financials_live(record_id: str | None) -> Source:
    return _live(
        f"Superintendencia de Compañías: estados financieros ({MCP_ORIGIN})",
        NOT_DECLARED,
        SUPERCIAS_URL,
        record_id,
        "Se conservan el ejercicio fiscal, los empleados, el patrimonio y los activos.",
    )


def sri_live(record_id: str | None) -> Source:
    return _live(
        f"SRI: consulta pública del RUC ({MCP_ORIGIN})",
        NOT_DECLARED,
        SRI_LIVE_URL,
        record_id,
        "La consulta pública no expone declaraciones, ventas, retenciones ni pagos.",
    )


def sercop_pair_awards(record_id: str | None) -> Source:
    return sercop("SERCOP datos abiertos OCDS: adjudicaciones entre la entidad y el proveedor", record_id)


def vector_index(record_id: str | None) -> Source:
    return Source(
        dataset=(
            "Veedor: índice de procesos similares "
            "(incrustaciones locales de la clasificación y, cuando hay, la descripción del objeto)"
        ),
        licence=VEEDOR_LICENCE,
        retrieved_at=None,
        record_id=record_id,
        note="La similitud es semántica y no equivale a que el objeto contratado sea idéntico.",
    )


def contraloria_reports(record_id: str | None) -> Source:
    return _live(
        f"Contraloría General del Estado: informes aprobados ({MCP_ORIGIN})",
        NOT_DECLARED,
        CONTRALORIA_URL,
        record_id,
        "El servicio entrega como máximo una parte de las filas de cada archivo; la revisión es parcial.",
    )


def sercop_enquiries(record_id: str | None) -> Source:
    return sercop("SERCOP datos abiertos OCDS: preguntas y respuestas (recuentos y fechas)", record_id)


INVESTIGATION_SOURCES = {
    "supercias_company": supercias_company_live,
    "supercias_financials": supercias_financials_live,
    "sri_live": sri_live,
    "sercop_pair_awards": sercop_pair_awards,
    "vector_index": vector_index,
    "contraloria_reports": contraloria_reports,
    "sercop_enquiries": sercop_enquiries,
}
