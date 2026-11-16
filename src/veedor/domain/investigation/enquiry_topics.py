"""Fixed topics of the question-and-answer stage (pure data).

A question is assigned to the topic whose description it is closest to (embedding cosine) when that similarity
reaches `TOPIC_FLOOR`; otherwise it has no topic. The descriptions are neutral and are not shown to anyone.
The floor was measured, not chosen: see `docs/AGENTS.md` ("Enquiries specialist") and
`veedor investigate calibrate-topics`.
"""

from __future__ import annotations

TOPIC_DESCRIPTIONS_ES: dict[str, str] = {
    "deadlines": (
        "Plazos y fechas: prórroga del plazo, ampliación de la fecha de cierre de ofertas, cronograma, "
        "días para presentar la oferta y para entregar el bien o servicio."
    ),
    "specifications": (
        "Especificaciones técnicas: características del bien o servicio, marca, modelo, ficha técnica, "
        "medidas, cantidades, normas y términos de referencia."
    ),
    "price": (
        "Precio y presupuesto: presupuesto referencial, valor unitario, forma de pago, anticipo, "
        "reajuste de precios, impuestos y costos."
    ),
    "requirements": (
        "Requisitos para participar: experiencia mínima del oferente, certificados, documentos, "
        "personal técnico, formularios y causas de descalificación."
    ),
}
TOPIC_ORDER: tuple[str, ...] = tuple(TOPIC_DESCRIPTIONS_ES)

# Cosine similarity a question needs to be counted under a topic. Measured on a sample of real questions
# (see docs/AGENTS.md); a ranking aid, not a finding.
TOPIC_FLOOR = 0.40
LATE_WINDOW_DAYS = 3
MAX_PLAUSIBLE_ANSWER_DAYS = 3_650
