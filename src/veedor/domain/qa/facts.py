# ruff: noqa: E501
"""Candidate facts for one process: the dossier's own sentences, with provenance and retrieval keys (pure).

The sentences come from `domain.dossier.template.catalogue`: the same renderer that writes the dossier, so the
wording rules (no accusation, no unverified claim, « » only around attributed source text) stay enforced here.
This module adds, per fact:

* `fact_id`, `section` and `text` exactly as the dossier renders them;
* `source_id` and `source_field`, taken from the provenance catalogue (`domain.provenance.catalog`);
* `keys`: short Spanish phrases used to *rank* the fact against a question (never shown);
* `model_text`: the sentence with every « » span replaced, because text between « » comes from the data
  (a CPC description, an activity, a report title) and a model must not read third-party text.

Natural persons never reach this module as data: the pack is already masked, and a fact whose sentence still
holds a personal identifier is dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from veedor.domain.dossier.investigation_facts import OMITTED_QUOTE, SPEC_BY_ID, UNTRUSTED_QUOTE_IDS
from veedor.domain.dossier.models import EvidencePack
from veedor.domain.dossier.template import catalogue
from veedor.domain.investigation.identifiers import document_has_personal_identifier
from veedor.domain.provenance import catalog
from veedor.domain.signals import SIGNALS_BY_CODE

_QUOTE = re.compile(r"«[^»]*»")
MAX_MODEL_TEXT_CHARS = 420

# fact id -> retrieval phrases (what a visitor might ask that this sentence answers).
FACT_KEYS_ES: dict[str, str] = {
    "process.object": "qué se contrató; objeto del contrato; qué compró la entidad; qué se está comprando; descripción del objeto de la contratación; en qué consiste el proceso; qué producto o servicio se adquirió",
    "process.entity": "entidad contratante; quién contrató; quién compró; quién es el comprador; RUC de la entidad; en qué provincia está la entidad; dónde queda la entidad contratante; qué institución hizo la compra",
    "process.procedure": "procedimiento de contratación; método de contratación; tipo de proceso; categoría del proceso; estado del proceso; cómo se contrató; qué modalidad se usó; subasta inversa o licitación",
    "process.amounts": "presupuesto referencial; monto adjudicado; cuánto se adjudicó; cuánto costó; valor del contrato; cuánto dinero se gastó; qué porcentaje del presupuesto se adjudicó; precio final; por cuánto se contrató",
    "process.tenderers": "número de oferentes; cuántos oferentes hubo; cuántas empresas participaron; cuántas ofertas se presentaron; inicio de ofertas; cierre de ofertas; fecha límite para presentar ofertas; cuándo cerró el plazo de ofertas",
    "process.award_dates": "fecha de adjudicación; cuándo se adjudicó el proceso; fecha de firma del contrato; cuándo se firmó el contrato; en qué fecha se adjudicó",
    "process.cpc": "código CPC; clasificación del producto; descripción de la clasificación CPC; qué código CPC tiene el proceso",
    "signals.none": "no se detectaron señales de riesgo; el proceso no tiene señales; tiene alguna alerta; hay señales de riesgo",
    "signals.unavailable": "señales de riesgo no disponibles",
    "winner.identity": "quién ganó; quién ganó el proceso; proveedor adjudicado; adjudicatario; a quién se adjudicó; quién es el proveedor ganador; RUC del proveedor; nombre de la empresa ganadora",
    "winner.sri": "estado del proveedor en el SRI; actividad económica del proveedor; cuándo inició actividades la empresa; en qué provincia está el proveedor; tipo de contribuyente; a qué se dedica la empresa ganadora; está activo el RUC del proveedor",
    "winner.ghost": "listado de empresas fantasmas del SRI; figura el proveedor en la lista de empresas fantasmas; el ganador está en el catastro del SRI",
    "winner.company": "tipo de compañía del proveedor; qué tipo de empresa es el ganador; Superintendencia de Compañías; es sociedad anónima o limitada",
    "winner.revenue": "ingresos del proveedor; ventas de la empresa; cuánto factura la empresa ganadora; ingresos del año del proceso; tamaño económico del proveedor",
    "relation.previous": "adjudicaciones previas entre la entidad y el proveedor; historial entre la entidad y el proveedor; el proveedor había ganado antes con esta entidad; contratos anteriores con la misma entidad; había contratado antes la entidad a esta empresa",
    "relation.pair_total": "total de adjudicaciones de la entidad al proveedor; cuántas veces ha ganado esta empresa con esta entidad; relación entre la entidad y el proveedor",
    "relation.unavailable": "historial entre la entidad y el proveedor no disponible",
    "context.count": "cuántos procesos del mismo procedimiento y año hay; procesos comparables; con qué procesos se compara este; cuántos procesos parecidos existen",
    "context.median_tenderers": "mediana de oferentes; cuántos oferentes suele haber en procesos parecidos; número típico de oferentes en el mismo procedimiento",
    "context.single_bidder_share": "proporción de procesos con un solo oferente; qué porcentaje de procesos tiene oferente único; qué tan común es que haya un solo oferente",
    "context.median_ratio": "relación típica entre monto adjudicado y presupuesto; mediana del ahorro; qué tan cerca del presupuesto se adjudica normalmente",
    "context.unavailable": "estadísticas comparativas no disponibles",
    "investigation.company.legal_status": "situación legal de la empresa; está activa la compañía; en qué estado legal está el proveedor; disolución o liquidación",
    "investigation.company.incorporation": "cuándo se constituyó la empresa; fecha de constitución del proveedor; antigüedad de la compañía; cuántos días tenía la empresa cuando se adjudicó; es una empresa nueva",
    "investigation.company.capital": "capital suscrito de la empresa; cuánto capital tiene la compañía ganadora; relación entre el monto adjudicado y el capital",
    "investigation.company.filing": "último balance presentado por la empresa; en qué año presentó su último balance",
    "investigation.financials.latest": "estados financieros de la empresa; cuántos empleados tiene el proveedor; patrimonio del proveedor; activos de la empresa ganadora",
    "investigation.tax.live": "consulta en línea al SRI; estado del RUC según el SRI; clase de contribuyente; categoría de la empresa; cese de actividades",
    "investigation.tax.matches_download": "coincide el estado del SRI en línea con el listado descargado",
    "investigation.pair.others": "otras adjudicaciones de la entidad al proveedor en cualquier fecha; cuánto ha recibido el proveedor de esta entidad; monto acumulado de adjudicaciones al proveedor",
    "investigation.similar.window": "compras similares de la misma entidad; hubo compras parecidas cerca de la fecha; compras repartidas del mismo objeto",
    "investigation.audit.count": "informes de la Contraloría sobre la entidad; auditorías a la entidad compradora; exámenes especiales de la Contraloría",
    "investigation.enquiries.count": "cuántas preguntas hicieron los oferentes; número de preguntas del proceso; cuántas preguntas fueron respondidas; cómo fue la etapa de preguntas y respuestas",
    "investigation.enquiries.timing": "cuántos días tardó la entidad en responder; tiempo de respuesta a las preguntas de los oferentes; demora en contestar",
    "investigation.enquiries.late": "preguntas recibidas cerca del cierre de ofertas; llegaron preguntas de último momento; preguntas en los últimos días antes del cierre",
    "investigation.enquiries.topics": "de qué trataron las preguntas; temas de las preguntas de los oferentes; cuántas preguntas fueron sobre plazos, especificaciones, precio o requisitos",
}

# fact id -> keys of the provenance catalogue it is made of (for process, winner and registry facts).
_PROVENANCE_KEYS: dict[str, tuple[str, ...]] = {
    "process.object": ("facts.main_cpc_description",),
    "process.entity": ("facts.buyer_name", "facts.buyer_ruc", "facts.buyer_region", "facts.buyer_locality"),
    "process.procedure": ("facts.method", "facts.category", "facts.status"),
    "process.amounts": ("facts.budget", "facts.award_total"),
    "process.tenderers": ("facts.n_tenderers", "facts.tender_start", "facts.tender_end"),
    "process.award_dates": ("facts.first_award_date", "facts.date_signed"),
    "process.cpc": ("facts.main_cpc", "facts.main_cpc_description"),
    "signals.none": ("score.n_signals",),
    "signals.unavailable": ("score.n_signals",),
    "winner.identity": ("winner.name", "winner.ruc", "winner.kind"),
    "winner.sri": ("registry.sri_status", "registry.sri_taxpayer_type", "registry.sri_activity_start"),
    "winner.ghost": ("registry.sri_ghost_listed",),
    "winner.company": ("registry.supercias_company_type",),
    "winner.revenue": ("registry.supercias_revenue_latest", "registry.supercias_revenue_year"),
}
_OCDS_RELATION = ("sercop_ocds", "awards[].suppliers[].id; awards[].date; buyer.id")
_CONTEXT = (
    "veedor_indicators",
    "processes (mismo método y año): recuentos y medianas calculados por Veedor sobre los datos abiertos",
)


@dataclass(frozen=True, slots=True)
class QaFact:
    fact_id: str
    section: str
    text: str
    model_text: str
    keys: str
    source_id: str
    source_field: str

    @property
    def key_phrases(self) -> tuple[str, ...]:
        """The retrieval keys, one phrase each: a short phrase is closer to a short question than a list."""
        return tuple(p.strip() for p in self.keys.split(";") if p.strip())


def _spec_for(key: str) -> catalog.FactSpec | None:
    if key in catalog.FACTS:
        return catalog.FACTS[key]
    return catalog.REGISTRY_FACTS[key][1] if key in catalog.REGISTRY_FACTS else None


def provenance_of(fact_id: str) -> tuple[str, str] | None:
    """``(source_id, source_field)`` of a catalogue fact, or ``None`` when the fact has no entry."""
    if fact_id.startswith("signal:"):
        code = fact_id.split(":", 1)[1]
        return ("veedor_indicators", catalog.signal_source_field(code)) if code in SIGNALS_BY_CODE else None
    if fact_id in _PROVENANCE_KEYS:
        specs = [s for s in map(_spec_for, _PROVENANCE_KEYS[fact_id]) if s is not None]
        if not specs:
            return None
        fields = "; ".join(dict.fromkeys(s.source_field.replace("{sri_file}", "SRI_RUC_<provincia>.zip") for s in specs))
        return specs[0].source_id, fields
    if fact_id.startswith("relation."):
        return _OCDS_RELATION
    if fact_id.startswith("context."):
        return _CONTEXT
    if fact_id.startswith("investigation."):
        spec = SPEC_BY_ID.get(fact_id)
        if spec is None:
            return None
        tool, field = catalog.investigation_tool(fact_id)
        source = spec.source_key if spec.source_key in catalog.SOURCES else "veedor_indicators"
        return source, f"{tool}: {field}"
    return None


def _keys_for(fact_id: str, text: str) -> str:
    if fact_id in FACT_KEYS_ES:
        return FACT_KEYS_ES[fact_id]
    if fact_id.startswith("signal:"):
        definition = SIGNALS_BY_CODE.get(fact_id.split(":", 1)[1])
        if definition is not None:
            return (
                f"{definition.label_es}; señal de riesgo {definition.label_es}; por qué tiene esta señal; "
                f"qué significa la señal; {definition.description_es}"
            )
    spec = SPEC_BY_ID.get(fact_id)
    return spec.label_es if spec is not None else text[:120]


def model_text(text: str) -> str:
    """The sentence as a model may read it: no span quoted from the data, bounded length."""
    shown = _QUOTE.sub(OMITTED_QUOTE, text)
    return shown if len(shown) <= MAX_MODEL_TEXT_CHARS else shown[:MAX_MODEL_TEXT_CHARS].rstrip() + "…"


def build_facts(pack: EvidencePack) -> list[QaFact]:
    """Every fact the answer may state about this pack, in the dossier's default order.

    Dropped: facts that quote third-party text as their content (the Contraloría report list), and any
    sentence that still holds a personal identifier."""
    out: list[QaFact] = []
    for fact in catalogue(pack):
        if fact.id in UNTRUSTED_QUOTE_IDS or document_has_personal_identifier(fact.text):
            continue
        provenance = provenance_of(fact.id)
        if provenance is None:
            continue  # a fact without provenance is never shown (a test lists every id that has none)
        out.append(
            QaFact(
                fact_id=fact.id,
                section=fact.section,
                text=fact.text,
                model_text=model_text(fact.text),
                keys=_keys_for(fact.id, fact.text),
                source_id=provenance[0],
                source_field=provenance[1],
            )
        )
    return out
