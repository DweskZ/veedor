# ruff: noqa: E501
"""Provenance catalogue: for every fact the process page shows, its source, its exact field and how to check it.

Pure data. The use case `queries.provenance` fills in the per-process values and the per-process
choices (which budget path was really used, which signals fired). Nothing is invented here: OCDS paths
come from `infrastructure/ocds/flatten.py` (the only code that reads the bulk file), registry columns from
`docs/DATA_SOURCES.md`, and source metadata from `domain/dossier/source_catalog.py`.

A test (`tests/domain/test_provenance_catalog.py`) fails when a field of the process detail response has
no entry here, so a new fact cannot ship without its provenance.
"""

from __future__ import annotations

from dataclasses import dataclass

from veedor.domain.dossier import source_catalog as sc
from veedor.domain.dossier.investigation_facts import FACT_SPECS
from veedor.domain.signals import SIGNALS


@dataclass(frozen=True, slots=True)
class SourceInfo:
    id: str
    name: str
    publisher: str
    licence: str
    url: str | None


SERCOP_LICENCE = f"{sc.SERCOP_LICENCE} (vía el Open Contracting Data Registry)"

SOURCES: dict[str, SourceInfo] = {
    s.id: s
    for s in (
        SourceInfo(
            "sercop_ocds",
            "Datos abiertos de contratación pública (OCDS)",
            "SERCOP (Servicio Nacional de Contratación Pública)",
            SERCOP_LICENCE,
            sc.SERCOP_URL,
        ),
        SourceInfo(
            "sri_ruc",
            "SRI: registro de contribuyentes (RUC)",
            "SRI (Servicio de Rentas Internas)",
            sc.NOT_DECLARED,
            "https://www.sri.gob.ec/datasets",
        ),
        SourceInfo(
            "sri_ghost_list",
            "SRI: catastro de empresas fantasmas",
            "SRI (Servicio de Rentas Internas)",
            sc.NOT_DECLARED,
            "https://www.sri.gob.ec/datasets",
        ),
        SourceInfo(
            "supercias_directory",
            "Superintendencia de Compañías: directorio de compañías",
            "Superintendencia de Compañías, Valores y Seguros",
            sc.NOT_DECLARED,
            sc.SUPERCIAS_URL,
        ),
        SourceInfo(
            "supercias_ranking",
            "Superintendencia de Compañías: ranking de compañías (estados financieros)",
            "Superintendencia de Compañías, Valores y Seguros",
            sc.NOT_DECLARED,
            sc.SUPERCIAS_URL,
        ),
        SourceInfo(
            "veedor_indicators",
            "Veedor: indicadores y puntaje calculados sobre los datos anteriores",
            "Veedor",
            sc.VEEDOR_LICENCE,
            None,
        ),
        SourceInfo(
            "supercias_company",
            "Superintendencia de Compañías: directorio (consulta en línea)",
            "Superintendencia de Compañías, Valores y Seguros",
            sc.NOT_DECLARED,
            sc.SUPERCIAS_URL,
        ),
        SourceInfo(
            "supercias_financials",
            "Superintendencia de Compañías: estados financieros (consulta en línea)",
            "Superintendencia de Compañías, Valores y Seguros",
            sc.NOT_DECLARED,
            sc.SUPERCIAS_URL,
        ),
        SourceInfo(
            "sri_live",
            "SRI: consulta pública del RUC (consulta en línea)",
            "SRI (Servicio de Rentas Internas)",
            sc.NOT_DECLARED,
            sc.SRI_LIVE_URL,
        ),
        SourceInfo(
            "sercop_pair_awards",
            "Datos abiertos OCDS: adjudicaciones entre la entidad y el proveedor",
            "SERCOP (Servicio Nacional de Contratación Pública)",
            SERCOP_LICENCE,
            sc.SERCOP_URL,
        ),
        SourceInfo(
            "vector_index",
            "Veedor: índice de procesos similares",
            "Veedor",
            sc.VEEDOR_LICENCE,
            None,
        ),
        SourceInfo(
            "sercop_enquiries",
            "Datos abiertos OCDS: preguntas y respuestas del proceso (recuentos y fechas)",
            "SERCOP (Servicio Nacional de Contratación Pública)",
            SERCOP_LICENCE,
            sc.SERCOP_URL,
        ),
        SourceInfo(
            "contraloria_reports",
            "Contraloría General del Estado: informes aprobados (consulta en línea)",
            "Contraloría General del Estado",
            sc.NOT_DECLARED,
            sc.CONTRALORIA_URL,
        ),
    )
}

# Sources whose retrieval date is the day of a stored investigation, not the data download day.
LIVE_SOURCES = frozenset(
    {"supercias_company", "supercias_financials", "sri_live", "contraloria_reports", "vector_index", "sercop_enquiries"}
)
# Sources computed by Veedor: their date is the date of the last build.
DERIVED_SOURCES = frozenset({"veedor_indicators"})


@dataclass(frozen=True, slots=True)
class FactSpec:
    label_es: str
    source_id: str
    source_field: str
    derived: bool
    derivation_es: str | None
    verify_es: str


VERIFY_PROCESS = (
    "Busque el código del proceso ({process_code}) en el Portal de Compras Públicas de SERCOP, o el "
    "identificador {ocid} en los datos abiertos del Open Contracting Data Registry"
)
_VERIFY_OCDS = VERIFY_PROCESS + " (campo {field})."


def _ocds(label: str, path: str, *, derived: bool = False, derivation: str | None = None) -> FactSpec:
    return FactSpec(label, "sercop_ocds", path, derived, derivation, _VERIFY_OCDS.replace("{field}", path))


def _veedor(label: str, source_field: str, derivation: str, verify: str) -> FactSpec:
    return FactSpec(label, "veedor_indicators", source_field, True, derivation, verify)


# --- process facts (`facts.<field>` of the process detail response) ---------------------------------
FACTS: dict[str, FactSpec] = {
    "facts.process_code": _ocds("Código del proceso", "tender.id (si falta, tender.title)"),
    "facts.release_date": _ocds("Fecha de publicación", "date"),
    "facts.year": _ocds(
        "Año",
        "tender.tenderPeriod.startDate (si falta, date)",
        derived=True,
        derivation="Año de la fecha de inicio de ofertas; si el proceso no la publica, año de la fecha de publicación.",
    ),
    "facts.buyer_ruc": _ocds(
        "RUC de la entidad contratante", "buyer.id", derivation="Los 13 dígitos tras «EC-RUC-»."
    ),
    "facts.buyer_name": _ocds("Entidad contratante", "buyer.name"),
    "facts.buyer_region": _ocds("Provincia de la entidad", "parties[id = buyer.id].address.region"),
    "facts.buyer_locality": _ocds("Localidad de la entidad", "parties[id = buyer.id].address.locality"),
    "facts.method": _ocds(
        "Método de contratación", "tender.procurementMethodDetails (si falta, tender.procurementMethod)"
    ),
    "facts.method_group": FactSpec(
        "Grupo del método",
        "sercop_ocds",
        "tender.procurementMethodDetails",
        True,
        "Veedor agrupa el método con una tabla fija: los que empiezan por «Catálogo electrónico» son catálogo; "
        "los de adjudicación sin competencia por diseño son directos; los que reciben ofertas son competitivos; "
        "el resto es «otro».",
        VERIFY_PROCESS + ". Compare el método publicado con el grupo indicado.",
    ),
    "facts.category": _ocds("Categoría", "tender.mainProcurementCategory"),
    "facts.status": _ocds("Estado del proceso", "tender.status"),
    "facts.description": _ocds(
        "Descripción",
        "tender.description",
        derived=True,
        derivation="Primeros 600 caracteres del texto publicado; se omite si contiene datos personales.",
    ),
    "facts.description_withheld": _veedor(
        "Descripción omitida por datos personales",
        "tender.description",
        "Veedor omite la descripción cuando un participante del proceso es una persona natural o cuando "
        "detecta un nombre, una cédula o un RUC de persona natural en el texto.",
        "Abra el proceso en el Portal de Compras Públicas y lea la descripción original.",
    ),
    "facts.budget": _ocds("Presupuesto referencial", "tender.value.amount"),  # path replaced per process
    "facts.tender_start": _ocds("Inicio de ofertas", "tender.tenderPeriod.startDate"),
    "facts.tender_end": _ocds("Cierre de ofertas", "tender.tenderPeriod.endDate"),
    "facts.n_tenderers": _ocds("Número de oferentes", "tender.numberOfTenderers"),
    "facts.n_bids": _ocds(
        "Número de ofertas", "bids.details", derived=True, derivation="Cantidad de elementos de bids.details."
    ),
    "facts.n_awards": _ocds(
        "Número de adjudicaciones", "awards", derived=True, derivation="Cantidad de elementos de awards."
    ),
    "facts.award_total": _ocds(
        "Monto adjudicado",
        "awards[].value.amount",
        derived=True,
        derivation="Suma de los montos de todas las adjudicaciones; vacío si ninguna publica un monto.",
    ),
    "facts.first_award_date": _ocds(
        "Primera fecha de adjudicación",
        "awards[].date",
        derived=True,
        derivation="La fecha más antigua entre las adjudicaciones.",
    ),
    "facts.date_signed": _ocds(
        "Fecha de firma del contrato",
        "contracts[].dateSigned",
        derivation="La primera fecha de firma publicada.",
    ),
    "facts.main_cpc": _ocds(
        "Clasificación CPC principal",
        "tender.items[0].classification.id",
        derivation="Clasificación del primer ítem del proceso.",
    ),
    "facts.main_cpc_description": _ocds(
        "Descripción de la clasificación CPC",
        "tender.items[0].classification.description",
        derivation="Primeros 300 caracteres de la descripción del primer ítem.",
    ),
    # --- score ---
    "score.risk_score": _veedor(
        "Puntaje de riesgo",
        "process_scores.risk_score",
        "Suma de los pesos de las señales de riesgo activadas, con un máximo de 100. Los pesos son criterios "
        "de Veedor pendientes de calibración (docs/METHODOLOGY.md). Las señales de contexto no suman.",
        "Sume los pesos de las señales de riesgo listadas en este proceso (docs/METHODOLOGY.md).",
    ),
    "score.n_signals": _veedor(
        "Número de señales de riesgo",
        "process_signals",
        "Cantidad de señales de riesgo activadas (sin contar las de contexto).",
        "Cuente las señales de riesgo listadas en este proceso.",
    ),
    "score.n_context_signals": _veedor(
        "Número de señales de contexto",
        "process_signals",
        "Cantidad de señales de contexto activadas; no forman parte del puntaje.",
        "Cuente las señales de contexto listadas en este proceso.",
    ),
    "score.context_signal_codes": _veedor(
        "Señales de contexto",
        "process_signals.signal_code",
        "Códigos de las señales de contexto activadas.",
        "Compare con la lista de señales de este proceso.",
    ),
    "score.anomaly_score": _veedor(
        "Puntaje de anomalía",
        "process_scores.anomaly_score",
        "Puntaje de un modelo de aislamiento (Isolation Forest) sobre características numéricas del proceso. "
        "Se informa aparte y no cambia el puntaje de riesgo.",
        "No se puede verificar a mano: depende del modelo (docs/METHODOLOGY.md).",
    ),
    # --- winner (supplier profile; aggregates over the awards table) ---
    "winner.ruc": _ocds(
        "RUC del adjudicatario", "awards[].suppliers[].id", derivation="Los 13 dígitos tras «EC-RUC-»."
    ),
    "winner.name": _ocds("Adjudicatario", "awards[].suppliers[].name"),
    "winner.kind": FactSpec(
        "Tipo de proveedor",
        "veedor_indicators",
        "awards[].suppliers[].id",
        True,
        "Tercer dígito del RUC: 0 a 5 persona natural, 6 entidad pública, 9 sociedad. Sin RUC válido se trata "
        "como no identificado.",
        "Revise el tercer dígito del RUC del adjudicatario.",
    ),
}


def _profile(label: str, derivation: str) -> FactSpec:
    return _veedor(
        label,
        "awards.parquet agregado por RUC",
        derivation,
        "Busque el RUC del adjudicatario en los datos abiertos de SERCOP y repita el conteo o la suma.",
    )


FACTS.update(
    {
        "winner.n_processes": _profile("Procesos del proveedor", "Procesos en los que el RUC participa como oferente o adjudicatario."),
        "winner.n_wins": _profile("Adjudicaciones del proveedor", "Procesos distintos adjudicados al RUC."),
        "winner.total_awarded": _profile("Total adjudicado al proveedor", "Suma de los montos de sus adjudicaciones."),
        "winner.first_award_date": _profile("Primera adjudicación del proveedor", "La fecha más antigua de sus adjudicaciones."),
        "winner.last_award_date": _profile("Última adjudicación del proveedor", "La fecha más reciente de sus adjudicaciones."),
        "winner.n_buyers": _profile("Entidades que le adjudicaron", "Entidades contratantes distintas de sus adjudicaciones."),
        "winner.top_buyer_ruc": _profile("Entidad con más adjudicaciones", "RUC de la entidad que más monto le adjudicó."),
        "winner.top_buyer_share": _profile("Participación de esa entidad", "Monto de la entidad principal dividido por el total adjudicado al proveedor."),
        "winner.single_bidder_wins": _profile("Adjudicaciones con oferente único", "Adjudicaciones en procesos con un solo oferente."),
        "winner.mean_risk_score": _profile("Puntaje medio de sus procesos", "Promedio del puntaje de riesgo de sus procesos."),
        # --- tenderers and awards (lists) ---
        "tenderers.ruc": _ocds("RUC de los oferentes", "tender.tenderers[].id", derivation="Los 13 dígitos tras «EC-RUC-»."),
        "tenderers.name": _ocds("Oferentes", "tender.tenderers[].name"),
        "tenderers.kind": FactSpec(
            "Tipo de oferente", "veedor_indicators", "tender.tenderers[].id", True,
            "Tercer dígito del RUC: 0 a 5 persona natural, 6 entidad pública, 9 sociedad.",
            "Revise el tercer dígito del RUC de cada oferente.",
        ),
        "awards.award_id": _ocds("Identificador de la adjudicación", "awards[].id"),
        "awards.award_date": _ocds("Fecha de la adjudicación", "awards[].date"),
        "awards.supplier_ruc": _ocds("RUC del proveedor adjudicado", "awards[].suppliers[].id", derivation="Los 13 dígitos tras «EC-RUC-»."),
        "awards.supplier_name": _ocds("Proveedor adjudicado", "awards[].suppliers[].name"),
        "awards.amount": _ocds(
            "Monto de cada adjudicación", "awards[].value.amount",
            derivation="Vacío cuando una adjudicación lista varios proveedores: la fuente no reparte el monto.",
        ),
    }
)  # fmt: skip


# --- winner registry facts (company or public entity only; natural persons are never looked up) --------
_VERIFY_RUC = "Busque el RUC {ruc} en {where}."
REGISTRY_FACTS: dict[str, tuple[str, FactSpec]] = {
    "registry.sri_status": (
        "sri_ruc",
        FactSpec(
            "Estado del contribuyente en el SRI", "sri_ruc", "{sri_file}: ESTADO_CONTRIBUYENTE", False,
            "Es el estado vigente cuando se publicó el archivo, no el que tenía al momento de la adjudicación.",
            _VERIFY_RUC.replace("{where}", "la consulta pública de RUC del SRI o en el archivo indicado"),
        ),
    ),
    "registry.sri_activity_start": (
        "sri_ruc",
        FactSpec(
            "Inicio de actividades en el SRI", "sri_ruc", "{sri_file}: FECHA_INICIO_ACTIVIDADES", False, None,
            _VERIFY_RUC.replace("{where}", "la consulta pública de RUC del SRI o en el archivo indicado"),
        ),
    ),
    "registry.sri_taxpayer_type": (
        "sri_ruc",
        FactSpec(
            "Tipo de contribuyente en el SRI", "sri_ruc", "{sri_file}: TIPO_CONTRIBUYENTE", False, None,
            _VERIFY_RUC.replace("{where}", "la consulta pública de RUC del SRI o en el archivo indicado"),
        ),
    ),
    "registry.sri_ghost_listed": (
        "sri_ghost_list",
        FactSpec(
            "Figura en el catastro de empresas fantasmas del SRI", "sri_ghost_list",
            "SRI_Catastro_Empresas_Fantasmas.csv: NUMERO_RUC", False,
            "Es un hecho de registro: aparece o no el RUC en el listado. No es una conclusión sobre el contrato.",
            _VERIFY_RUC.replace("{where}", "el catastro de empresas fantasmas publicado por el SRI"),
        ),
    ),
    "registry.supercias_company_type": (
        "supercias_directory",
        FactSpec(
            "Tipo de compañía", "supercias_directory", "bi_compania.csv: tipo", False, None,
            _VERIFY_RUC.replace("{where}", "el directorio de compañías de la Superintendencia de Compañías"),
        ),
    ),
    "registry.supercias_revenue_latest": (
        "supercias_ranking",
        FactSpec(
            "Ingresos por ventas más recientes reportados", "supercias_ranking", "bi_ranking.csv: ingresos_ventas",
            False,
            "Último ejercicio con ingresos informados en el archivo; puede ser posterior al proceso.",
            _VERIFY_RUC.replace("{where}", "el ranking de compañías de la Superintendencia de Compañías"),
        ),
    ),
    "registry.supercias_revenue_year": (
        "supercias_ranking",
        FactSpec(
            "Ejercicio fiscal de esos ingresos", "supercias_ranking", "bi_ranking.csv: anio", False, None,
            _VERIFY_RUC.replace("{where}", "el ranking de compañías de la Superintendencia de Compañías"),
        ),
    ),
}  # fmt: skip


# --- signals --------------------------------------------------------------------------------------
# Lake column of a signal input -> where the value comes from. Every column used by a signal needs an entry.
COLUMN_SOURCE: dict[str, str] = {
    "processes.method_group": "tender.procurementMethodDetails (agrupado por Veedor)",
    "processes.n_tenderers": "tender.numberOfTenderers",
    "processes.tender_start": "tender.tenderPeriod.startDate",
    "processes.tender_end": "tender.tenderPeriod.endDate",
    "processes.method": "tender.procurementMethodDetails",
    "processes.year": "tender.tenderPeriod.startDate (año)",
    "processes.award_total": "awards[].value.amount (suma)",
    "processes.budget": "tender.value.amount (o lotes, o planning.budget.amount.amount)",
    "processes.first_award_date": "awards[].date (la más antigua)",
    "processes.buyer_ruc": "buyer.id",
    "processes.main_cpc": "tender.items[0].classification.id",
    "awards.supplier_ruc": "awards[].suppliers[].id",
    "awards.amount": "awards[].value.amount",
    "tenderers.supplier_ruc": "tender.tenderers[].id",
    "suppliers_sri.activity_start_date": "SRI_RUC_<provincia>.zip: FECHA_INICIO_ACTIVIDADES",
    "suppliers_sri.status": "SRI_RUC_<provincia>.zip: ESTADO_CONTRIBUYENTE",
    "ghost_companies.ruc": "SRI_Catastro_Empresas_Fantasmas.csv: NUMERO_RUC",
    "ghost_companies.notification_date": "SRI_Catastro_Empresas_Fantasmas.csv: FECHA_NOTIFICACION_RESOLUCION",
    "company_financials.revenue": "bi_ranking.csv: ingresos_ventas",
    "company_financials.year": "bi_ranking.csv: anio",
}

VERIFY_SIGNAL = (
    "Con los campos indicados, repita el cálculo con los datos abiertos de SERCOP "
    "(proceso {process_code}, identificador {ocid}); la regla y el umbral están en la descripción."
)
VERIFY_SIGNAL_STATISTICAL = (
    VERIFY_SIGNAL + " El umbral es un percentil del método y año: se obtiene ordenando todos los procesos "
    "del mismo método y año con los datos abiertos."
)
VERIFY_SIGNAL_REGISTRY = (
    "Con los campos indicados, compare el dato del proceso (SERCOP, identificador {ocid}) con el registro "
    "público citado, buscando el RUC del adjudicatario."
)


def signal_input_columns(code: str) -> tuple[str, ...]:
    return next(s.fields for s in SIGNALS if s.code == code)


def signal_source_field(code: str) -> str:
    return "; ".join(f"{column} <- {COLUMN_SOURCE[column]}" for column in signal_input_columns(code))


def signal_verify(code: str) -> str:
    definition = next(s for s in SIGNALS if s.code == code)
    if definition.needs_registry:
        return VERIFY_SIGNAL_REGISTRY
    return VERIFY_SIGNAL_STATISTICAL if definition.statistical else VERIFY_SIGNAL


# --- investigation (stored by the CLI; values live in the dossier section "Investigación realizada") ---
INVESTIGATION_TOOLS: dict[str, tuple[str, str]] = {
    # fact id prefix -> (tool, field read)
    "investigation.company": ("get_compania_info", "situacion_legal, fecha_constitucion, capital_suscrito, ultimo_balance"),
    "investigation.financials": ("get_financials", "anio, ingresos_ventas, activos, patrimonio, n_empleados"),
    "investigation.tax": ("get_sri_ruc_info", "estado, clase_contribuyente, categoria_mipymes, fecha_inicio_actividades"),
    "investigation.pair": ("pair_awards", "awards.parquet (adjudicaciones de la entidad y el proveedor)"),
    "investigation.similar": ("similar_processes", "índice vectorial (procesos similares de la misma entidad)"),
    "investigation.audit": ("get_contraloria_informe", "informes aprobados (fecha, período, tipo)"),
    "investigation.enquiries": ("process_texts", "tender.enquiries[].date y dateAnswered; recuentos (el texto no se almacena)"),
    "investigation.run": ("(registro de la investigación)", "bitácora de especialistas y consultas"),
}  # fmt: skip


def investigation_tool(fact_id: str) -> tuple[str, str]:
    prefix = ".".join(fact_id.split(".")[:2])
    return INVESTIGATION_TOOLS[prefix]


def investigation_catalogue() -> dict[str, tuple[str | None, str]]:
    """Fact id -> (source id or None, label) for every fact the investigation can add."""
    return {spec.id: (spec.source_key, spec.label_es) for spec in FACT_SPECS}
