"""Closed vocabularies of the investigation layer (pure).

Everything a tool result can contribute to a pack, a dossier or a model prompt is mapped here to a
member of a closed set. A string that is not in the set becomes ``other``: it is never copied.
"""

from __future__ import annotations

from typing import Literal, get_args

from veedor.domain.dossier.models import LegalStatus, LookupOutcome, SriStatus
from veedor.domain.dossier.text import canonical

SpecialistName = Literal["company", "tax_registry", "history", "audit"]
SPECIALISTS: tuple[SpecialistName, ...] = get_args(SpecialistName)
TargetRef = Literal["winner", "buyer", "process"]
OUTCOMES: tuple[str, ...] = get_args(LookupOutcome)

ToolName = Literal[
    "get_compania_info",
    "get_financials",
    "get_sri_ruc_info",
    "pair_awards",
    "similar_processes",
    "list_catalogo",
    "get_contraloria_informe",
]
TOOLS: tuple[ToolName, ...] = get_args(ToolName)
MCP_TOOLS: frozenset[str] = frozenset(
    {"get_compania_info", "get_financials", "get_sri_ruc_info", "list_catalogo", "get_contraloria_informe"}
)

# Why a call was not made or returned nothing. Closed: it is stored and rendered.
Reason = Literal[
    "natural_person",
    "not_registry_eligible",
    "no_identifier",
    "budget_exhausted",
    "tool_not_allowed",
    "not_found",
    "server_unavailable",
    "vectors_unavailable",
    "not_indexed",
    "lake_unavailable",
    "no_buyer_name",
    "ambiguous_buyer_name",
    "no_reports_in_catalogue",
    "upstream_http_error",
    "tool_reported_error",
    "malformed_content",
    "schema_mismatch",
    "identifier_mismatch",
    "oversized_content",
    "out_of_range",
]

DispatchReason = Literal[
    "new_supplier_signal",
    "supplier_not_active_signal",
    "ghost_listing_signal",
    "company_size_signal",
    "buyer_concentration_signal",
    "repeated_awards_signal",
    "recurring_cobidders_signal",
    "single_bidder_signal",
    "tender_window_signal",
    "low_saving_signal",
    "baseline_check",
    "retry_after_transient_failure",
]
DISPATCH_REASONS: tuple[str, ...] = get_args(DispatchReason)

SPECIALIST_LABEL_ES: dict[str, str] = {
    "company": "registro de la compañía",
    "tax_registry": "registro tributario",
    "history": "historial de compras",
    "audit": "informes de control",
}

# Source keys appear in the "Investigación realizada" section. Each is a fixed Spanish label.
SOURCE_BY_TOOL: dict[str, str] = {
    "get_compania_info": "supercias_company",
    "get_financials": "supercias_financials",
    "get_sri_ruc_info": "sri_live",
    "pair_awards": "sercop_pair_awards",
    "similar_processes": "vector_index",
    "list_catalogo": "contraloria_catalogue",
    "get_contraloria_informe": "contraloria_reports",
}
SOURCE_LABEL_ES: dict[str, str] = {
    "supercias_company": "Superintendencia de Compañías (registro de la compañía)",
    "supercias_financials": "Superintendencia de Compañías (estados financieros)",
    "sri_live": "SRI (consulta en línea del RUC)",
    "sercop_pair_awards": "SERCOP (adjudicaciones entre la entidad y el proveedor)",
    "vector_index": "índice de procesos similares de Veedor",
    "contraloria_catalogue": "Contraloría General del Estado (catálogo de informes)",
    "contraloria_reports": "Contraloría General del Estado (informes aprobados)",
}
OUTCOME_PHRASE_ES: dict[str, str] = {
    "ok": "respondió",
    "timeout": "no respondió a tiempo",
    "upstream_error": "falló",
    "invalid_result": "devolvió una respuesta no válida, que se descartó",
    "skipped": "no se consultó",
}
REASON_PHRASE_ES: dict[str, str] = {
    "natural_person": "el proveedor es una persona natural",
    "not_registry_eligible": "el RUC no corresponde a una compañía o entidad pública",
    "no_identifier": "falta el identificador necesario",
    "budget_exhausted": "se agotó el presupuesto de consultas",
    "tool_not_allowed": "la herramienta no está permitida",
    "not_found": "la fuente no tiene registro",
    "server_unavailable": "el servidor de consulta no estuvo disponible",
    "vectors_unavailable": "el índice de procesos similares no está disponible",
    "not_indexed": "el proceso no está en el índice",
    "lake_unavailable": "los datos descargados no están disponibles",
    "no_buyer_name": "falta el nombre de la entidad",
    "ambiguous_buyer_name": "el nombre de la entidad es ambiguo",
    "no_reports_in_catalogue": "el catálogo no ofrece informes comparables",
    "upstream_http_error": "el servicio de origen devolvió un error",
    "tool_reported_error": "la herramienta informó un error",
    "malformed_content": "el contenido no tenía el formato esperado",
    "schema_mismatch": "el contenido no coincidía con el esquema esperado",
    "identifier_mismatch": "el registro devuelto no correspondía al identificador consultado",
    "oversized_content": "el contenido superaba el tamaño permitido",
    "out_of_range": "algún valor estaba fuera de rango y se descartó",
}
# Sentence used when a lookup produced no value.
UNAVAILABLE_ES = "no disponible (la fuente no respondió)"

# Contraloría report types appear as short words; any other value is dropped.
REPORT_TYPES: dict[str, str] = {
    "general": "general",
    "examen especial": "examen especial",
    "auditoria financiera": "auditoría financiera",
    "auditoria de gestion": "auditoría de gestión",
}


def _key(text: str) -> str:
    return " ".join(canonical(text).replace("_", " ").split())


def legal_status(raw: str | None) -> LegalStatus | None:
    """Map the registry's free legal-status string to a closed category; unknown text is ``other``."""
    if raw is None or not raw.strip():
        return None
    key = _key(raw)
    if "cancelad" in key or "inactiv" in key:
        return "cancelled_or_inactive"
    if "disolu" in key or "liquida" in key or "disuelt" in key:
        return "dissolution_or_liquidation"
    if key == "activa":
        return "active"
    return "other"


def sri_status(raw: str | None) -> SriStatus | None:
    if raw is None or not raw.strip():
        return None
    return {"activo": "active", "suspendido": "suspended", "cancelado": "cancelled"}.get(_key(raw), "other")


def taxpayer_class(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    return {"especial": "especial", "otro": "otro"}.get(_key(raw), "other")


def mipymes(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    mapping = {
        "micro": "micro",
        "pequena": "pequena",
        "mediana": "mediana",
        "grande": "grande",
        "no declarado": "no_declarado",
    }
    return mapping.get(_key(raw), "other")


def report_type(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    return REPORT_TYPES.get(_key(raw))
