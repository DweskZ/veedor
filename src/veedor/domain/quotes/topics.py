"""One short Spanish topic description per signal code (pure data).

A topic says what a *relevant passage* would talk about, in neutral words. It is embedded with the same
local model as the passages and compared by cosine similarity. A topic never states that the signal is
a problem: the quote is shown next to the signal as context, not as proof.

The wording is descriptive on purpose. Related codes share a topic where the published text of the
process can only speak about the same thing (for example, the two registry-listing codes).
"""

from __future__ import annotations

from veedor.domain.signals import SIGNALS_BY_CODE

_REGISTRY_STATUS = (
    "Situación del proveedor ante el SRI y la Superintendencia de Compañías: estado del RUC, habilitación, "
    "registro de contribuyentes y documentos habilitantes del oferente."
)
_CAPACITY = (
    "Capacidad financiera y técnica del oferente: patrimonio, ingresos, experiencia previa, índices "
    "financieros y monto del contrato frente a la capacidad exigida."
)

SIGNAL_TOPICS_ES: dict[str, str] = {
    "SINGLE_BIDDER": (
        "Requisitos de participación, experiencia exigida, especificaciones técnicas, marcas y modelos, "
        "condiciones para presentar la oferta y número de oferentes."
    ),
    "SHORT_TENDER_WINDOW": (
        "Plazos y prórrogas: fecha límite para presentar ofertas, ampliación del plazo, cronograma, "
        "días para preguntas y respuestas y fecha de cierre."
    ),
    "LOW_SAVING": (
        "Precio, presupuesto referencial, valor de la oferta, descuento, rebaja, puja y monto adjudicado."
    ),
    "NEW_SUPPLIER": (
        "Experiencia, antigüedad y trayectoria de la empresa, fecha de constitución, inicio de actividades "
        "y requisitos habilitantes del proveedor."
    ),
    "SUPPLIER_NOT_ACTIVE": _REGISTRY_STATUS,
    "GHOST_COMPANY_LIST": _REGISTRY_STATUS,
    "GHOST_COMPANY_LISTED_LATER": _REGISTRY_STATUS,
    "BUYER_CONCENTRATION": (
        "Adjudicación al mismo proveedor, contrataciones anteriores de la entidad, varios contratos del "
        "mismo proveedor y objeto contratado en procesos anteriores."
    ),
    "REPEATED_DIRECT_AWARDS": (
        "Contratación directa: causal o justificación, urgencia, contrataciones repetidas del mismo objeto "
        "y proveedor único."
    ),
    "RECURRING_COBIDDERS": (
        "Oferentes participantes, ofertas presentadas, calificación y evaluación de los oferentes y "
        "convocatorias anteriores."
    ),
    "CONTRACT_VS_COMPANY_SIZE": _CAPACITY,
    "CONTRACT_VS_COMPANY_SIZE_SAME_YEAR": _CAPACITY,
}


def topic_for(code: str) -> str:
    return SIGNAL_TOPICS_ES[code]


def missing_topics() -> list[str]:
    """Signal codes of the catalogue without a topic (the test suite requires an empty list)."""
    return sorted(set(SIGNALS_BY_CODE) - set(SIGNAL_TOPICS_ES))
