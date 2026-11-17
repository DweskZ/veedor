# ruff: noqa: E501
"""What a visitor can ask about one process, as intents (pure data and a lexical matcher).

The retrieval used to compare a question with the wording of its own keys (`FACT_KEYS_ES`): a question
phrased differently found nothing (docs/EVALUATION.md, review 5 finding 3). An *intent* is a kind of question
the stored evidence can answer (or, for `oos`, a kind it cannot), described two ways that do not depend on one
wording:

* `prototypes`: many differently worded example questions. A question is scored by the embedding similarity
  to the nearest prototype of each intent (`domain.qa.ranking`), not to a single key phrase;
* `terms`: accent-folded stems and short phrases with a weight (ganó, ganador, adjudicatario, ...). The
  lexical score of an intent is a noisy-or of the weights of the terms the question contains.

Both are fused in `domain.qa.ranking`. Every intent maps to the fact ids it is answered with. An intent whose
facts the process does not have still competes: a question that is really about an absent fact (the number of
employees, when no investigation is stored) is then not answered with a neighbouring fact.

Prototypes and terms are written from the domain (what the dossier states and how people in Ecuador talk about
public procurement). The development phrasings (`evaluation/qa/questions.py`, `DEV_*`) were used to tune them;
the held-out phrasings (`evaluation/qa/heldout.py`) were not, and a test asserts that none of these prototypes
equals or contains one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from veedor.domain.dossier.text import canonical
from veedor.domain.qa.facts import FACT_KEYS_ES

OOS_ID = "oos"  # kinds of question the stored evidence never answers
SIGNALS_ID = "signals_all"  # "which risk signals does it have": answered with every signal fact
SIGNAL_PREFIX = "signal:"


@dataclass(frozen=True, slots=True)
class IntentSpec:
    id: str
    facts: tuple[str, ...]  # fact ids answering it (empty: answered with nothing)
    prototypes: tuple[str, ...]
    terms: tuple[tuple[str, float], ...] = ()


def _t(*pairs: tuple[str, float]) -> tuple[tuple[str, float], ...]:
    return pairs


INTENTS: tuple[IntentSpec, ...] = (
    IntentSpec(
        "object", ("process.object",),
        (
            "qué es lo que se está comprando", "de qué trata el contrato", "explícame qué se pidió en este proceso",
            "descripción del bien o servicio", "qué producto estaban buscando", "en qué consiste la obra o el servicio",
            "qué tipo de cosa adquirió el estado", "qué necesitaban conseguir con este proceso", "cuál es la finalidad de la compra",
            "dime qué incluye la contratación", "de qué se trata esto", "qué artículo o trabajo se solicita",
            "para qué es esta contratación", "contenido del contrato",
        ),
        _t(("objeto", 0.6), ("que se compro", 0.6), ("que compraron", 0.6), ("que compro", 0.55), ("que adquir*", 0.55), ("adquir*", 0.35),
           ("comprando", 0.4), ("descripcion", 0.35), ("producto", 0.3), ("servicio", 0.25), ("en que consiste", 0.6), ("de que trata", 0.6),
           ("de que se trata", 0.6), ("de que es", 0.3), ("se contrato", 0.3), ("se esta contratando", 0.4), ("para que sirve", 0.3), ("para que va a servir", 0.3),
           ("pidieron", 0.3), ("pidio", 0.2), ("solicitad*", 0.35), ("necesit*", 0.25), ("cosa", 0.15), ("obra", 0.2), ("articulo", 0.3), ("en que gast*", 0.45), ("necesidad", 0.3), ("servir", 0.25), ("piden", 0.3), ("trabajo", 0.12)),
    ),
    IntentSpec(
        "entity", ("process.entity",),
        (
            "qué entidad pública está comprando", "quién es el comprador", "de qué institución es este proceso",
            "en qué lugar del país está la entidad que contrata", "datos de la entidad contratante", "quién publicó este proceso",
            "qué organismo del gobierno hace la compra", "a qué municipio o ministerio pertenece", "cuál es el ruc del comprador",
            "dónde queda la institución que contrata", "qué dependencia pide esto", "quién abre este concurso",
            "en qué provincia queda quien compra",
        ),
        _t(("entidad", 0.55), ("institucion", 0.5), ("organismo", 0.45), ("comprador", 0.6), ("contratante", 0.6), ("compradora", 0.6),
           ("ministerio", 0.35), ("municipio", 0.35), ("gad", 0.3), ("prefectura", 0.35), ("hospital", 0.3), ("universidad", 0.3),
           ("provincia", 0.4), ("ciudad", 0.3), ("ubicad*", 0.3), ("ubicacion", 0.3), ("queda", 0.3), ("dependencia", 0.4),
           ("quien compro", 0.6), ("quien compra", 0.6), ("quien contrata", 0.6), ("quien contrato", 0.55), ("quien pide", 0.4), ("quien pidio", 0.4),
           ("quien paga", 0.35), ("pagando", 0.25), ("oficina", 0.3), ("publica", 0.15), ("gobierno", 0.3), ("estado", 0.15), ("el pedido", 0.3), ("hizo el pedido", 0.4), ("esta pagando", 0.4), ("quien hizo", 0.3)),
    ),
    IntentSpec(
        "procedure", ("process.procedure",),
        (
            "qué método de contratación se aplicó", "por qué vía se hizo la compra", "en qué estado se encuentra el proceso",
            "es una subasta inversa, una licitación o contratación directa", "qué modalidad de compra pública es",
            "ya se terminó el proceso o sigue vigente", "bajo qué régimen se contrató", "qué tipo de procedimiento es",
            "cómo la entidad hizo esta compra", "fue por catálogo electrónico o por otro mecanismo", "la contratación es de bienes, obras o servicios",
            "en qué punto está el trámite", "qué categoría de proceso es", "procedimiento aplicado",
        ),
        _t(("procedimiento", 0.7), ("modalidad", 0.6), ("metodo", 0.5), ("tipo de proceso", 0.6), ("subasta", 0.5),
           ("licitacion", 0.45), ("menor cuantia", 0.6), ("catalogo", 0.4), ("categoria", 0.35), ("estado del proceso", 0.7),
           ("estado del tramite", 0.6), ("etapa", 0.35), ("fase", 0.35), ("tramite", 0.3), ("como se contrato", 0.4), ("como se compro", 0.4),
           ("ya termino", 0.3), ("sigue abierto", 0.35), ("vigente", 0.25), ("en curso", 0.35), ("finalizad*", 0.3), ("regimen", 0.35),
           ("figura legal", 0.4), ("mecanismo", 0.4), ("via", 0.15), ("directa", 0.3), ("bienes obras", 0.4), ("clase de tramite", 0.4), ("tipo de tramite", 0.4), ("figura", 0.2), ("hizo la compra", 0.3), ("hizo esto", 0.2)),
    ),
    IntentSpec(
        "amounts", ("process.amounts",),
        (
            "cuál fue el valor del contrato", "cuánta plata se destinó", "monto final de la adjudicación", "por qué cantidad de dólares se contrató",
            "cuánto estaba presupuestado", "el precio salió por debajo o por encima del presupuesto", "importe total de la compra",
            "qué suma de dinero se comprometió", "a cuánto asciende el contrato", "cuánto pagó el estado", "qué tanto del presupuesto se usó",
            "en qué valor se cerró esta contratación", "cuánto vale este proceso", "montos del proceso",
        ),
        _t(("monto", 0.6), ("montos", 0.6), ("presupuesto", 0.6), ("presupuestad*", 0.5), ("presupuestario", 0.5), ("valor", 0.35), ("precio", 0.5),
           ("costo", 0.5), ("costar*", 0.4), ("cuesta", 0.5), ("dolares", 0.5), ("plata", 0.4), ("dinero", 0.4), ("cifra", 0.35), ("importe", 0.6),
           ("adjudic*", 0.12), ("cuanto~adjudic*", 0.7), ("cuanto", 0.12), ("pago", 0.25), ("pagar", 0.25), ("pagaron", 0.3), ("techo", 0.4), ("gasto", 0.4), ("gastaron", 0.4),
           ("gastado", 0.4), ("total", 0.2), ("barato", 0.4), ("caro", 0.4), ("ahorro", 0.3), ("por cuanto", 0.4), ("en cuanto", 0.35), ("de cuanto", 0.35),
           ("a cuanto", 0.4), ("destinad*", 0.35), ("vale", 0.3), ("suma", 0.3), ("valores", 0.3)),
    ),
    IntentSpec(
        "tenderers", ("process.tenderers",),
        (
            "cuántos participantes tuvo el concurso", "cuántas ofertas se recibieron", "cuántas empresas se presentaron a competir",
            "hubo varios proveedores participando", "hasta qué fecha se aceptaban propuestas", "cuándo empezó y cuándo terminó el periodo de ofertas",
            "cuántos licitantes entraron", "fecha de apertura y cierre para ofertar", "qué tantos proveedores ofertaron", "cuántas propuestas llegaron al portal",
            "cuándo vencía el plazo para entregar la oferta", "participaron muchos oferentes", "cantidad de postulantes",
            "hubo más empresas compitiendo por el contrato", "quiénes más se postularon", "cuántos rivales tuvo la empresa ganadora", "alguien más concursó o fue una sola",
            "cuántas compañías quisieron participar",
        ),
        _t(("oferente", 0.55), ("oferentes", 0.55), ("oferta", 0.5), ("ofertas", 0.5), ("ofertar", 0.5), ("ofertaron", 0.5), ("postor*", 0.6), ("participante*", 0.45),
           ("participaron", 0.45), ("participo", 0.4), ("participar", 0.3), ("propuesta*", 0.45), ("licitante*", 0.55), ("concursante*", 0.55), ("postulante*", 0.5),
           ("competencia", 0.35), ("competidor*", 0.35), ("competir", 0.35), ("compit*", 0.5), ("competi*", 0.4), ("rival*", 0.45), ("postul*", 0.5), ("concursa*", 0.5), ("concurrencia", 0.4),
           ("mas empresas", 0.3), ("otras empresas", 0.3), ("mas proveedores", 0.3), ("otros proveedores", 0.3), ("presentarse", 0.4), ("participa*", 0.3), ("entraron", 0.25), ("se presentaron", 0.45), ("se presento", 0.4), ("se postularon", 0.5),
           ("se anotaron", 0.5), ("se inscribieron", 0.5), ("cuantas empresas", 0.4), ("cuantos proveedores", 0.4), ("cuanta gente", 0.4), ("plazo", 0.15),
           ("cierre", 0.25), ("recepcion", 0.3), ("limite", 0.2), ("hasta cuando", 0.25), ("hasta que dia", 0.3), ("hasta que fecha", 0.3), ("apertura", 0.3), ("mandaron", 0.25)),
    ),
    IntentSpec(
        "award_dates", ("process.award_dates",),
        (
            "cuándo se resolvió la adjudicación", "en qué fecha firmaron el contrato", "qué día se formalizó la compra", "cuándo se suscribió el contrato",
            "fecha en que quedó adjudicado", "en qué momento se le entregó el contrato al proveedor", "cuándo se concretó la contratación",
            "fechas de adjudicación y de firma", "qué día se oficializó el resultado", "cuándo salió la resolución de adjudicación", "a partir de qué fecha rige el contrato",
        ),
        _t(("fecha", 0.3), ("cuando", 0.25), ("cuando~adjudic*", 0.6), ("firmo", 0.45), ("firmaron", 0.45), ("firmado", 0.45), ("firma del contrato", 0.5), ("suscrib*", 0.4), ("suscripcion", 0.4), ("adjudic*", 0.15),
           ("resolucion", 0.3), ("se dieron", 0.3), ("dieron el contrato", 0.35), ("se cerro el trato", 0.4), ("formaliz*", 0.4), ("oficializ*", 0.4),
           ("se hizo oficial", 0.4), ("sellaron", 0.2), ("trato", 0.3), ("cerro el trato", 0.45), ("resolvio", 0.35), ("resuelve", 0.3), ("resuelto", 0.3), ("entregaron", 0.2), ("que dia", 0.25), ("en que mes", 0.3), ("dia", 0.1), ("momento", 0.1), ("concret*", 0.2)),
    ),
    IntentSpec(
        "cpc", ("process.cpc",),
        (
            "qué número de clasificación de producto tiene", "código del clasificador central de productos", "a qué grupo del clasificador pertenece lo comprado",
            "en qué categoría del catálogo de productos entra", "cuál es el código cpc", "clasificación del producto contratado", "número de cpc del objeto",
            "qué rubro del clasificador de productos es",
        ),
        _t(("cpc", 0.9), ("central de productos", 0.8), ("clasificacion", 0.4), ("clasificador", 0.5), ("clasificad*", 0.3), ("codigo", 0.25), ("rubro", 0.2),
           ("grupo de productos", 0.35), ("categoria de producto", 0.35)),
    ),
    IntentSpec(
        "winner", ("winner.identity",),
        (
            "quién resultó ganador", "a qué empresa le adjudicaron", "cuál es la compañía que se quedó con el contrato", "quién va a ejecutar el trabajo",
            "nombre y ruc del adjudicado", "qué proveedor fue elegido", "quién obtuvo la adjudicación", "a quién le dieron esto", "cuál fue la empresa seleccionada",
            "quién se ganó el concurso", "datos del proveedor adjudicado", "quién fue el contratista escogido", "qué firma se llevó la obra",
        ),
        _t(("quien~gano", 0.85), ("quienes~ganaron", 0.85), ("quien~se llevo", 0.8), ("quien~se quedo con", 0.8), ("quien~obtuvo", 0.7), ("quien~resulto", 0.65),
           ("a quien~dieron", 0.7), ("a quien~adjudic*", 0.8), ("quien~adjudicatari*", 0.8), ("quien~escogid*", 0.7), ("quien~seleccionad*", 0.7), ("quien~elegid*", 0.7),
           ("quien~favorecid*", 0.7), ("a que empresa~adjudic*", 0.7), ("que empresa~gano", 0.7), ("que empresa~escogid*", 0.7), ("que empresa~seleccionad*", 0.7),
           ("que compania~gano", 0.7), ("que proveedor~elegid*", 0.7), ("que proveedor~escogid*", 0.7), ("que proveedor~seleccionad*", 0.7), ("que proveedor~gano", 0.7),
           ("gano", 0.3), ("ganador*", 0.35), ("ganaron", 0.3), ("ganar", 0.15), ("adjudicatari*", 0.4), ("adjudicad*", 0.12), ("adjudicaron", 0.3),
           ("proveedor*", 0.2), ("contratista*", 0.3), ("escogid*", 0.25), ("seleccionad*", 0.25), ("elegid*", 0.25), ("favorecid*", 0.25), ("razon social", 0.6), ("le toco", 0.35),
           ("resulto", 0.15), ("quien", 0.1), ("a quien", 0.2), ("obtuvo", 0.25), ("se gano", 0.3), ("empresa", 0.12), ("compania", 0.12), ("ejecutar", 0.3), ("ejecutor*", 0.4),
           ("se llevo", 0.25), ("se quedo con", 0.3)),
    ),
    IntentSpec(
        "registry_sri", ("winner.sri",),
        (
            "cuál es el estado del proveedor ante el servicio de rentas internas", "a qué se dedica la empresa adjudicada", "desde cuándo funciona esa empresa",
            "el ruc del proveedor está vigente", "qué actividad económica registra el ganador", "en qué provincia está registrada la empresa ganadora",
            "qué tipo de contribuyente es el adjudicatario", "cuándo inició sus actividades el contratista", "está activo en el SRI", "giro del negocio del proveedor",
            "situación tributaria del proveedor",
        ),
        _t(("sri", 0.5), ("ruc", 0.3), ("activo", 0.25), ("vigente", 0.2), ("suspendid*", 0.3), ("cancelad*", 0.3), ("actividad", 0.4), ("actividades", 0.4), ("economica", 0.3),
           ("giro", 0.5), ("dedica", 0.45), ("dedican", 0.45), ("a que se dedica", 0.6), ("contribuyente*", 0.5), ("tributari*", 0.4), ("rentas", 0.35), ("fisco", 0.3),
           ("rentas internas", 0.5), ("empezo", 0.2), ("comenzo", 0.2), ("abrio", 0.3), ("opera", 0.3), ("funciona", 0.3), ("rubro", 0.25), ("de que vive", 0.5), ("en que rubro", 0.4),
           ("en que trabaja", 0.4), ("puertas", 0.2)),
    ),
    IntentSpec(
        "ghost", ("winner.ghost",),
        (
            "el proveedor está en el listado de empresas fantasma", "la compañía es una de las que el SRI marcó como inexistentes", "aparece en la lista de contribuyentes con transacciones inexistentes",
            "figura como empresa ficticia en el catastro", "es una empresa de papel según las autoridades tributarias", "está en la lista negra del SRI",
            "el ganador emite facturas falsas según el SRI", "sale como fantasma", "listado de compañías inexistentes",
        ),
        _t(("fantasma*", 0.85), ("inexistente*", 0.75), ("ficticia", 0.6), ("ficticio", 0.6), ("de papel", 0.5), ("lista negra", 0.5), ("facturas falsas", 0.7), ("apocrif*", 0.7),
           ("catastro", 0.5), ("transacciones inexistentes", 0.8), ("listado", 0.15), ("lista", 0.1), ("sri", 0.1)),
    ),
    IntentSpec(
        "registry_company", ("winner.company",),
        (
            "qué clase de sociedad es la empresa ganadora", "es una compañía anónima o de responsabilidad limitada", "cómo está registrada la empresa en la superintendencia de compañías",
            "qué forma jurídica tiene el proveedor", "tipo de compañía del adjudicado", "es una sociedad anónima", "la empresa es una cia ltda", "qué figura societaria tiene el contratista",
            "de qué tipo de empresa se trata según la supercias",
        ),
        _t(("anonima", 0.7), ("limitada", 0.55), ("cia", 0.4), ("ltda", 0.6), ("sociedad", 0.35), ("sociedades", 0.35), ("compania", 0.2), ("tipo de compania", 0.6), ("tipo de sociedad", 0.6),
           ("tipo de empresa", 0.55), ("juridic*", 0.45), ("supercias", 0.65), ("superintendencia", 0.65), ("forma legal", 0.45), ("societari*", 0.55), ("corporacion", 0.4),
           ("fundacion", 0.3), ("acciones simplificada", 0.6), ("clase de sociedad", 0.6), ("clase de compania", 0.6), ("clase de empresa", 0.5)),
    ),
    IntentSpec(
        "revenue", ("winner.revenue",),
        (
            "cuánto vende la empresa al año", "ingresos anuales del proveedor", "qué tan grande es la facturación de la compañía", "ventas de la firma adjudicada en el año",
            "tamaño económico del contratista", "cuánto dinero mueve esa empresa", "cuánto factura el ganador",
        ),
        _t(("ingresos", 0.8), ("ingreso", 0.7), ("ventas", 0.6), ("factura*", 0.5), ("facturacion", 0.55), ("tamano", 0.3), ("economicamente", 0.3), ("cuanto vende", 0.6),
           ("utilidad*", 0.3), ("mueve", 0.3), ("ganancias", 0.3), ("anual*", 0.15)),
    ),
    IntentSpec(
        "history", ("relation.previous", "relation.pair_total", "relation.unavailable"),
        (
            "ya habían contratado antes a esta empresa", "cuántas veces le ha adjudicado esta entidad a este proveedor", "contratos anteriores entre el comprador y el ganador",
            "es la primera vez que la entidad trabaja con esta compañía", "tiene antecedentes de adjudicaciones con la misma institución", "esa institución le ha dado trabajo antes a este contratista",
            "relación comercial previa entre las dos partes", "el proveedor repite con la entidad", "adjudicaciones pasadas a este proveedor por esta entidad",
            "han hecho negocios otras veces", "cuántos contratos previos tienen",
        ),
        _t(("antes", 0.3), ("previo", 0.4), ("previa", 0.4), ("previas", 0.4), ("previos", 0.4), ("anterior*", 0.4), ("pasado", 0.3), ("pasados", 0.3), ("historial", 0.5),
           ("historia", 0.3), ("habia ganado", 0.5), ("ya habia", 0.3), ("veces", 0.3), ("repetid*", 0.4), ("repite", 0.35), ("seguido", 0.25), ("recurrente*", 0.35),
           ("otra vez", 0.3), ("de nuevo", 0.25), ("relacion", 0.3), ("conocian", 0.4), ("conocidos", 0.4), ("primera vez", 0.5), ("vinculo", 0.35), ("nexo", 0.3), ("cliente", 0.3),
           ("le han dado", 0.3), ("entidad", 0.1), ("antecedente*", 0.4), ("de antes", 0.4), ("otras veces", 0.35), ("vendido", 0.25),
           ("dado trabajo", 0.4), ("ya se conocian", 0.5), ("misma empresa", 0.2), ("compras le han", 0.3), ("contratado antes", 0.5)),
    ),
    IntentSpec(
        "context_count", ("context.count", "context.unavailable"),
        (
            "cuántos casos hay en el grupo de comparación", "con cuántos procesos parecidos se contrastó este", "qué tan grande es la muestra de referencia",
            "en qué cantidad de compras similares se basan las estadísticas", "número de procesos del mismo tipo que sirven de base", "tamaño del grupo con el que se compara",
        ),
        _t(("comparable*", 0.5), ("comparar", 0.45), ("comparacion", 0.45), ("comparan", 0.45), ("compara", 0.45), ("comparado", 0.45), ("referencia", 0.35), ("contrast*", 0.45), ("grupo", 0.3),
           ("muestra", 0.35), ("cuantos procesos", 0.4), ("cuantos casos", 0.4), ("cuantas compras", 0.35), ("cuantos ejemplos", 0.4), ("mismo tipo", 0.12), ("mismo metodo", 0.15),
           ("similares", 0.12), ("parecidos", 0.12), ("iguales", 0.12), ("base", 0.2), ("universo", 0.35), ("estadistica*", 0.25)),
    ),
    IntentSpec(
        "context_tenderers", ("context.median_tenderers",),
        (
            "cuál es la cantidad usual de participantes en contrataciones parecidas", "normalmente cuántas ofertas reciben procesos como este",
            "promedio de oferentes en otros procesos del mismo tipo", "qué tan concurridas son estas compras por lo general", "mediana del número de oferentes en casos similares",
            "cuántos proveedores suelen presentarse en este tipo de contratación",
        ),
        _t(("mediana", 0.4), ("tipico", 0.35), ("tipicamente", 0.35), ("normalmente", 0.35), ("habitual*", 0.35), ("suele", 0.35), ("suelen", 0.35), ("generalmente", 0.35),
           ("promedio", 0.35), ("usual", 0.35), ("en general", 0.3), ("lo normal", 0.4), ("por lo general", 0.35), ("concurrid*", 0.35), ("oferentes", 0.2), ("participantes", 0.2),
           ("postores", 0.2), ("ofertas", 0.15), ("competencia", 0.15), ("propuestas", 0.15), ("esperad*", 0.25), ("otros concursos", 0.3), ("postulan", 0.2), ("otros", 0.1), ("parecid*", 0.15), ("similar*", 0.15)),
    ),
    IntentSpec(
        "context_single", ("context.single_bidder_share",),
        (
            "qué tan frecuente es que compita un único proveedor en compras así", "proporción de procesos parecidos con un solo participante", "en cuántos casos similares hubo un solo postor",
            "con qué frecuencia ocurre que nadie más se presenta", "es común que no haya competencia en este tipo de contratación", "porcentaje de procesos comparables con un oferente único",
        ),
        _t(("un solo", 0.5), ("unico*", 0.5), ("unica", 0.5), ("solo uno", 0.5), ("uno solo", 0.5), ("solitari*", 0.4), ("sin competencia", 0.5), ("nada mas uno", 0.5),
           ("oferente unico", 0.6), ("porcentaje", 0.25), ("proporcion", 0.3), ("frecuencia", 0.3), ("seguido", 0.2), ("comun", 0.25), ("frecuente", 0.25), ("raro", 0.2),
           ("de cada cien", 0.4), ("similares", 0.15), ("parecidos", 0.15), ("mismo tipo", 0.12)),
    ),
    IntentSpec(
        "context_ratio", ("context.median_ratio",),
        (
            "qué tan cerca del presupuesto suelen adjudicar este tipo de procesos", "cuánto se ahorra normalmente en compras parecidas", "relación habitual entre lo adjudicado y lo presupuestado",
            "mediana del descuento sobre el presupuesto", "en procesos comparables, qué porcentaje del presupuesto se adjudica",
        ),
        _t(("ahorro", 0.35), ("descuento", 0.4), ("rebaja", 0.4), ("ratio", 0.5), ("cerca del presupuesto", 0.5), ("normalmente", 0.2), ("habitual*", 0.2), ("comparables", 0.2), ("sobre el presupuesto", 0.3)),
    ),
    IntentSpec(
        "context_compare", ("context.count", "context.median_tenderers", "context.single_bidder_share", "context.median_ratio", "context.unavailable"),
        (
            "esto es normal o es raro comparado con otros procesos", "cómo se compara este proceso con otros parecidos", "en qué posición queda frente a compras similares",
            "se sale de lo común respecto a procesos del mismo tipo", "qué tan distinto es de otros procesos iguales", "cómo está frente a otros concursos del mismo método",
            "es típico para este tipo de proceso", "cómo se ve en comparación con el resto de procesos", "dónde se ubica este proceso entre los comparables",
        ),
        _t(("comparado con", 0.6), ("comparada con", 0.6), ("comparados con", 0.5), ("en comparacion", 0.6), ("se compara", 0.55), ("comparar*", 0.35), ("frente a otr*", 0.6),
           ("frente a procesos", 0.55), ("frente a compras", 0.55), ("respecto a otr*", 0.55), ("respecto a procesos", 0.55), ("contra otros", 0.5), ("con otros procesos", 0.5),
           ("otros procesos", 0.3), ("procesos parecidos", 0.35), ("procesos similares", 0.35), ("del mismo tipo", 0.3), ("se sale de lo comun", 0.5), ("fuera de lo comun", 0.5),
           ("posicion", 0.35), ("tipico", 0.3), ("normal", 0.15), ("raro", 0.15), ("esperable", 0.3), ("del resto", 0.3), ("el resto de procesos", 0.4), ("en que posicion", 0.5)),
    ),
    IntentSpec(
        SIGNALS_ID, ("signals.none", "signals.unavailable"),
        (
            "qué señales de alerta se detectaron", "tiene indicadores de riesgo", "qué banderas rojas aparecen", "por qué salió marcado este proceso en el análisis",
            "cuáles son las alertas de este proceso", "algún semáforo en rojo para esta contratación", "cuáles indicadores saltaron en este proceso", "resumen de señales", "qué riesgos se detectaron",
            "me muestras todas las alertas", "hay advertencias sobre este proceso",
        ),
        _t(("senales", 0.7), ("senal", 0.5), ("alerta", 0.6), ("alertas", 0.6), ("bandera*", 0.7), ("rojas", 0.3), ("rojo", 0.3), ("semaforo*", 0.6), ("riesgo*", 0.5), ("indicador*", 0.55),
           ("sospech*", 0.4), ("anomal*", 0.4), ("alarma*", 0.5), ("advertencia*", 0.5), ("marcad*", 0.35), ("marcaron", 0.35), ("detectaron", 0.35), ("detectado*", 0.35),
           ("encontraron", 0.3), ("analisis", 0.15), ("fue mal", 0.3), ("todo lo que", 0.1), ("irregular*", 0.3)),
    ),
    # --- facts that exist only when an investigation of the process is stored -------------------------------------
    IntentSpec(
        "co_legal_status", ("investigation.company.legal_status",),
        ("cuál es la situación legal de la compañía", "la empresa está en disolución o liquidación", "en qué estado legal está la sociedad", "la compañía fue disuelta o está intervenida"),
        _t(("situacion legal", 0.6), ("estado legal", 0.6), ("disolucion", 0.6), ("liquidacion", 0.6), ("disuelta", 0.6), ("liquidada", 0.6), ("intervenida", 0.5)),
    ),
    IntentSpec(
        "co_incorporation", ("investigation.company.incorporation",),
        (
            "cuándo se fundó esa empresa", "qué edad tiene la compañía", "es una empresa recién formada", "hace cuántos años existe el proveedor", "en qué año se creó la sociedad",
            "cuántos días de constituida tenía cuando le adjudicaron", "fecha de creación de la compañía", "es una empresa con trayectoria",
        ),
        _t(("constitu*", 0.6), ("constituy*", 0.6), ("fundacion", 0.4), ("fundaron", 0.4), ("fundada", 0.4), ("creada", 0.35), ("se creo", 0.4), ("nacio", 0.4), ("antiguedad", 0.5),
           ("antigua", 0.4), ("vieja", 0.4), ("joven", 0.35), ("reciente", 0.35), ("recien", 0.35), ("nueva", 0.3), ("anos de vida", 0.5), ("anos tiene", 0.4), ("edad", 0.4),
           ("hace cuanto", 0.35), ("hace poco", 0.35), ("dias tenia", 0.5), ("trayectoria", 0.4), ("existe", 0.2), ("existen", 0.2), ("nace", 0.3), ("armo", 0.2), ("fundo", 0.4)),
    ),
    IntentSpec(
        "co_capital", ("investigation.company.capital",),
        (
            "con cuánto dinero se formó la compañía", "capital suscrito de la sociedad", "qué capital tiene registrado la empresa ganadora", "cuánto aportaron los socios al inicio",
            "relación entre el valor del contrato y el capital social de la sociedad", "monto del contrato comparado con el capital social",
        ),
        _t(("capital", 0.8), ("patrimonio", 0.35), ("aporte*", 0.35), ("aportado", 0.35), ("suscrito", 0.4), ("pagado", 0.2), ("acciones", 0.15), ("de arranque", 0.3), ("al inicio", 0.1)),
    ),
    IntentSpec(
        "co_filing", ("investigation.company.filing",),
        ("cuál fue el último balance que presentó la empresa", "en qué año entregó sus estados financieros por última vez", "la compañía presentó su balance al día"),
        _t(("balance*", 0.6), ("ultimo ano", 0.2), ("presento", 0.2), ("presentado", 0.2), ("declaro", 0.15), ("declaracion", 0.15)),
    ),
    IntentSpec(
        "co_financials", ("investigation.financials.latest",),
        ("cuántos empleados tiene la empresa", "cuántos trabajadores emplea el proveedor", "activos y pasivos de la compañía ganadora", "patrimonio y utilidad de la firma"),
        _t(("empleados", 0.7), ("trabajadores", 0.55), ("personal", 0.4), ("nomina", 0.4), ("activos", 0.5), ("pasivos", 0.5), ("patrimonio", 0.4), ("financier*", 0.35),
           ("estados financieros", 0.4), ("cuantos empleados", 0.8), ("emplea", 0.5)),
    ),
    IntentSpec(
        "tax_live", ("investigation.tax.live",),
        ("qué dice la consulta en línea del SRI sobre el proveedor", "estado actual del ruc en la consulta directa", "clase de contribuyente según el SRI en línea", "la empresa cesó actividades"),
        _t(("en linea", 0.4), ("consulta en linea", 0.6), ("cese", 0.5), ("cesacion", 0.5), ("cesaron", 0.5), ("cesado", 0.5), ("clase de contribuyente", 0.5), ("actualizado", 0.25)),
    ),
    IntentSpec(
        "tax_matches", ("investigation.tax.matches_download",),
        ("coincide lo que dice el SRI en línea con el listado descargado", "el estado del SRI concuerda con el archivo descargado", "hay diferencia entre el SRI en línea y el listado"),
        _t(("coincide", 0.55), ("coinciden", 0.55), ("concuerda", 0.55), ("difiere", 0.5), ("discrepa", 0.5), ("distinto", 0.3), ("descargad*", 0.5), ("diferencia", 0.3)),
    ),
    IntentSpec(
        "pair_others", ("investigation.pair.others",),
        (
            "cuánto ha cobrado esta empresa de la entidad en total", "qué otros contratos tiene el proveedor con la misma institución", "suma de adjudicaciones de la entidad al proveedor en otros procesos",
            "monto acumulado que ha recibido de este comprador", "cuántos procesos más le han dado a esta compañía en esta entidad", "total pagado por la institución a la empresa en otras compras",
        ),
        _t(("otros procesos", 0.4), ("otras adjudicaciones", 0.5), ("otros contratos", 0.45), ("acumulad*", 0.45), ("en total", 0.2), ("cuanto ha recibido", 0.5), ("cuanto ha cobrado", 0.5),
           ("ha cobrado", 0.4), ("recibido", 0.3), ("mas le han", 0.35), ("adicionales", 0.3), ("ademas de este", 0.4), ("cobrado", 0.35), ("pagado", 0.2)),
    ),
    IntentSpec(
        "similar_window", ("investigation.similar.window",),
        ("hubo compras parecidas de la misma entidad en fechas cercanas", "se repartió la compra en varias contrataciones", "fraccionamiento de la compra", "compras del mismo objeto en la misma temporada"),
        _t(("fraccion*", 0.6), ("repartid*", 0.45), ("dividid*", 0.45), ("troceo", 0.6), ("fragment*", 0.5), ("mismo objeto", 0.35), ("fechas cercanas", 0.4), ("compras similares", 0.4), ("compras parecidas", 0.4)),
    ),
    IntentSpec(
        "audit_count", ("investigation.audit.count",),
        ("hay informes de la contraloría sobre la entidad compradora", "ha sido auditada la institución", "exámenes especiales a la entidad", "auditorías previas del organismo de control"),
        _t(("contraloria", 0.85), ("auditoria*", 0.6), ("audit*", 0.5), ("examen especial", 0.6), ("examenes especiales", 0.6), ("informes de", 0.2), ("revisaron", 0.2)),
    ),
    IntentSpec(
        "enq_count", ("investigation.enquiries.count",),
        (
            "cuántas dudas plantearon los proveedores", "hubo consultas durante el concurso", "cuántas aclaraciones solicitaron los participantes", "número de preguntas recibidas y contestadas",
            "cómo estuvo la fase de preguntas y respuestas", "se hicieron muchas consultas", "cuántos interrogantes enviaron los interesados",
        ),
        _t(("pregunta*", 0.7), ("consulta*", 0.55), ("aclaracion*", 0.45), ("aclarar", 0.4), ("duda*", 0.45), ("inquietud*", 0.45), ("interrogante*", 0.45), ("solicitaron", 0.2), ("respuestas", 0.4),
           ("cuantas preguntas", 0.85), ("foro", 0.3), ("portal", 0.15), ("contestadas", 0.45), ("respondidas", 0.45)),
    ),
    IntentSpec(
        "enq_timing", ("investigation.enquiries.timing",),
        (
            "cuánto se demoró la entidad en contestar las dudas", "en cuántos días respondieron a los proveedores", "qué tan rápido atendieron las consultas", "tiempo que tardaron en dar respuesta a las preguntas",
            "contestaron a tiempo", "días de demora en las respuestas",
        ),
        _t(("tard*", 0.35), ("demor*", 0.4), ("respond*", 0.4), ("contest*", 0.4), ("respuesta*", 0.35), ("atend*", 0.35), ("tiempo de respuesta", 0.6), ("rapido", 0.35),
           ("lento", 0.35), ("veloz", 0.35), ("rapidez", 0.35), ("a tiempo", 0.3), ("dias", 0.1), ("pregunta*", 0.15), ("consulta*", 0.15), ("duda*", 0.15)),
    ),
    IntentSpec(
        "enq_late", ("investigation.enquiries.late",),
        (
            "llegaron consultas cuando ya casi cerraba el plazo", "preguntas enviadas poco antes de cerrar el periodo", "hubo preguntas de último momento", "las dudas se acumularon en los días finales",
            "consultas pegadas a la fecha límite",
        ),
        _t(("ultimo momento", 0.55), ("ultima hora", 0.55), ("ultimos dias", 0.5), ("tarde", 0.3), ("tardia*", 0.5), ("tardio*", 0.5), ("pegad*", 0.4),
           ("vispera", 0.4), ("cerca del cierre", 0.5), ("cierre", 0.15), ("finales", 0.3), ("pregunta*", 0.15), ("consulta*", 0.15), ("duda*", 0.15), ("fecha limite", 0.3)),
    ),
    IntentSpec(
        "enq_topics", ("investigation.enquiries.topics",),
        ("de qué temas fueron las preguntas de los oferentes", "las dudas eran sobre plazos, precios o requisitos", "sobre qué asuntos consultaron los participantes", "clasificación de las preguntas por tema"),
        _t(("temas", 0.5), ("tema", 0.5), ("sobre que", 0.3), ("trataron", 0.5), ("asuntos", 0.4), ("motivos", 0.3), ("especificaciones", 0.3), ("requisitos", 0.3), ("pregunta*", 0.2), ("consulta*", 0.2), ("duda*", 0.2)),
    ),
    # --- what the stored evidence never answers ------------------------------------------------------------------
    IntentSpec(
        OOS_ID, (),
        (
            "cuántos días de plazo hay para entregar el trabajo", "qué garantía ofrece el proveedor", "de qué marca es el producto", "cómo se paga el contrato", "cuánto va construido de la obra",
            "en qué dirección queda el lugar de entrega", "cuál es el código interno del contrato", "qué exige el pliego de condiciones", "qué opina el público de esta compra", "hubo multas o sanciones al contratista",
            "cuántas personas trabajarán en el proyecto", "qué impuestos se pagaron", "cuántos kilómetros se construirán", "quién supervisa la ejecución", "en qué estado está la ejecución del contrato",
            "cuál es la capital de un país", "cómo está el clima hoy", "qué hora es", "cuéntame un chiste", "una receta de cocina", "cuánto es una operación de matemáticas",
            "recomiéndame una película", "traduce esta frase", "quién es el presidente de otro país", "cuánto está el dólar", "qué día es hoy", "cuál es la montaña más alta",
            "qué dicen los términos de referencia",
            "quién ganó las elecciones presidenciales", "cuál es el idioma que se habla en otro país", "cuántos habitantes tiene una ciudad", "cuál es el animal más rápido",
            "cómo se escribe una palabra", "cuál es el sujeto de una oración gramatical", "a cuánto está el bitcoin", "quién fundó una empresa tecnológica famosa",
            "cuándo es el próximo partido de la selección", "cómo se prepara un plato típico", "cuál es la distancia entre dos ciudades", "qué significa una palabra en inglés",
            "cuál es la fórmula de un compuesto químico", "quién inventó el teléfono", "cuánto cuesta un pasaje o un boleto", "dónde nació un personaje famoso",
            "cuál es el mejor lugar para vacacionar", "cómo funciona un motor", "cuál es el valor de una constante matemática", "quién ganó el premio de la academia",
        ),
        _t(("plazo de entrega", 0.6), ("plazo del contrato", 0.6), ("tiempo de entrega", 0.6), ("dias de entrega", 0.6), ("garantia*", 0.6), ("marca*", 0.5), ("forma de pago", 0.6),
           ("formas de pago", 0.6), ("como se paga", 0.5), ("multa*", 0.5), ("sancion*", 0.5), ("penalidad*", 0.5), ("avance", 0.5), ("ejecucion", 0.3), ("entregar", 0.3), ("entrega", 0.25),
           ("lugar de entrega", 0.5), ("donde se entrega", 0.5), ("numero de contrato", 0.55), ("numero del contrato", 0.55), ("codigo del contrato", 0.55), ("pliego*", 0.5), ("requisitos minimos", 0.5),
           ("experiencia", 0.35), ("satisf*", 0.5), ("impuesto*", 0.5), ("iva", 0.4), ("kilometro*", 0.5), ("metros", 0.3), ("dimension*", 0.4), ("supervis*", 0.4), ("fiscaliz*", 0.4), ("clima", 0.7), ("mundial", 1.0), ("campeonato", 0.5),
           ("chiste*", 0.7), ("receta*", 0.7), ("pelicula*", 0.7), ("musica", 0.6), ("presidente", 0.35), ("capital de", 0.5), ("dolar hoy", 0.6), ("traduc*", 0.7),
           ("que hora es", 0.7), ("que dia es hoy", 0.7), ("terminos de referencia", 0.55),
           ("oracion*", 0.6), ("gramatic*", 0.6), ("verbo", 0.5), ("sustantivo", 0.6), ("adjetivo", 0.6), ("sinonimo*", 0.6), ("sujeto", 0.3), ("objeto directo", 0.7), ("valor de pi", 0.8),
           ("elecciones", 0.7), ("nobel", 0.7), ("oscar", 0.6), ("futbol", 0.6), ("partido", 0.4), ("seleccion", 0.3), ("de hoy", 0.5), ("hoy", 0.3), ("matricula", 0.5), ("colegio", 0.4),
           ("rentable", 0.4), ("bitcoin", 0.7), ("boleto*", 0.5), ("pasaje*", 0.4), ("vuelo*", 0.4), ("avion", 0.4), ("celular*", 0.3), ("gasolina", 0.5), ("petroleo", 0.5), ("receta*", 0.7),
           ("famos*", 0.4), ("cantante*", 0.6), ("actor", 0.4), ("actriz", 0.5), ("cancion*", 0.6), ("habitantes", 0.5), ("idioma*", 0.6), ("animal*", 0.5), ("planeta*", 0.6), ("universo", 0.5),
           ("quimic*", 0.6), ("fisica", 0.5), ("historia de", 0.4), ("inventor*", 0.6), ("invento", 0.5), ("deporte*", 0.6), ("equipo de", 0.3), ("cual es el mejor", 0.4)),
    ),
)

INTENT_BY_ID: dict[str, IntentSpec] = {spec.id: spec for spec in INTENTS}
FACT_INTENTS: dict[str, tuple[str, ...]] = {}
for _spec in INTENTS:
    for _fact in _spec.facts:
        FACT_INTENTS[_fact] = (*FACT_INTENTS.get(_fact, ()), _spec.id)
FACT_INTENT: dict[str, str] = {fact: ids[0] for fact, ids in FACT_INTENTS.items()}  # the first (most specific) intent of a fact


def intent_of_fact(fact_id: str) -> str | None:
    """The intent a fact answers. Signal facts answer a question about that one signal (`None`: ranked by
    their own keys), `signals.*` facts answer the generic signals question."""
    return FACT_INTENT.get(fact_id)


def prototype_phrases() -> list[str]:
    """Every prototype question."""
    return [phrase for spec in INTENTS for phrase in spec.prototypes]


def lexical_phrases() -> list[str]:
    """Every multiword lexical term (a concept phrase such as "en que consiste", never a whole question)."""
    return [t.replace("~", " ").rstrip("*") for spec in INTENTS for t, _ in spec.terms if " " in t or "~" in t]


def key_phrases_of(spec: IntentSpec) -> list[str]:
    """The prototypes plus the retrieval keys the intent's facts always had (they stay prototypes)."""
    keys = [p.strip() for fact in spec.facts for p in FACT_KEYS_ES.get(fact, "").split(";") if p.strip()]
    return [*spec.prototypes, *keys]


# --- the lexical matcher --------------------------------------------------------------------------------------


def fold_text(text: str) -> str:
    """Lowercase, accents stripped, punctuation to spaces."""
    return " ".join(re.sub(r"[^0-9a-z]+", " ", canonical(text)).split())


def _compile(term: str) -> re.Pattern[str]:
    """`word*` is a prefix; `a~b` is `a` then `b` with up to three words between them ("quién se lo ganó")."""
    prefix = term.endswith("*")

    def piece(text: str) -> str:
        return re.escape(text.rstrip("*")).replace(r"\ ", " ") + ("[a-z0-9]*" if text.endswith("*") else "")

    body = r"(?: [a-z0-9]+){0,3} ".join(piece(part) for part in term.split("~"))
    return re.compile(rf"(?<![a-z0-9]){body}{'' if prefix else '(?![a-z0-9])'}")


_COMPILED: dict[str, list[tuple[re.Pattern[str], float]]] = {
    spec.id: [(_compile(term), weight) for term, weight in spec.terms] for spec in INTENTS
}


SHORT_QUESTION_WORDS = 2  # a question this short is all topic: its terms count more
SHORT_BOOST = 1.5
_FUNCTION_WORDS = frozenset("a al ante con de del el en es esa ese esta este la las le lo los me mi no o para por que se si su un una y ya como hay".split())


def lexical_scores(text: str) -> dict[str, float]:
    """Noisy-or of the weights of the terms of each intent found in the question (0 when none)."""
    folded = fold_text(text)
    boost = SHORT_BOOST if sum(w not in _FUNCTION_WORDS for w in folded.split()) <= SHORT_QUESTION_WORDS else 1.0
    out: dict[str, float] = {}
    for intent_id, compiled in _COMPILED.items():
        miss = 1.0
        for pattern, weight in compiled:
            if pattern.search(folded):
                miss *= 1.0 - weight
        out[intent_id] = min(1.0, (1.0 - miss) * boost)
    return out


# --- what is embedded --------------------------------------------------------------------------------------------

def embedding_variants(text: str) -> list[str]:
    """What is embedded for a phrase or a question: as written and folded (informal spelling drops accents)."""
    plain = canonical(text)
    return list(dict.fromkeys(v for v in (text, plain) if v))
