# ruff: noqa: E501
"""The answer: fixed sentences, closed vocabularies and the shape of a response (pure).

Every character an answer shows comes from one of three places: a fixed sentence below, a fact sentence written
by the dossier renderer, or a stored quote shown verbatim and attributed. A model contributes only the choice
of fact ids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

NO_EVIDENCE_ES = (
    "La evidencia almacenada de este proceso no responde a esa pregunta. Puedo responder sobre el objeto y los "
    "montos, los oferentes y las fechas, las señales de riesgo y su explicación, el proveedor adjudicado y su "
    "historial con la entidad, el contexto de procesos comparables y, cuando existen, la investigación "
    "almacenada y las preguntas y respuestas publicadas."
)
NO_JUDGEMENT_ES = (
    "Veedor describe registros y señales de riesgo; no emite juicios sobre personas ni entidades ni sobre si "
    "un proceso fue correcto o incorrecto. Puede preguntar por los datos del proceso, por ejemplo cuántos "
    "oferentes hubo, cuánto se adjudicó o por qué tiene una señal."
)
NO_PERSONS_ES = (
    "Veedor no ofrece datos de personas naturales (nombres, identificaciones, contactos o cargos). Solo "
    "describe registros del proceso, de empresas y de entidades públicas."
)
NOT_PROCESSABLE_ES = (
    "No se puede procesar esa pregunta. Escríbala como una pregunta sencilla sobre los datos de este proceso."
)
UNAVAILABLE_ES = (
    "Respuesta no disponible: no pudo verificarse contra la evidencia almacenada de este proceso."
)
ANSWERED_NOTE_ES = (
    "Respuesta compuesta solo con la evidencia almacenada de este proceso; cada frase indica su fuente. "
    "Describe registros y señales de riesgo y no emite juicios."
)

Mode = str  # "model" | "retrieval"
MODE_MODEL = "model"
MODE_RETRIEVAL = "retrieval"


class Reason(StrEnum):
    """Why the answer is what it is. Closed set: it is logged, counted and returned."""

    ANSWERED = "answered"
    NO_EVIDENCE = "no_evidence"
    JUDGEMENT = "judgement"
    PERSON = "person"
    INSTRUCTION = "instruction"
    UNVERIFIED = "unverified"


FIXED_SENTENCES: dict[Reason, str] = {
    Reason.NO_EVIDENCE: NO_EVIDENCE_ES,
    Reason.JUDGEMENT: NO_JUDGEMENT_ES,
    Reason.PERSON: NO_PERSONS_ES,
    Reason.INSTRUCTION: NOT_PROCESSABLE_ES,
    Reason.UNVERIFIED: UNAVAILABLE_ES,
}

# What the model may say about its own choice. A closed set: any other value invalidates the reply.
MODEL_REASONS: tuple[str, ...] = ("directa", "parcial", "sin_datos", "juicio", "fuera_de_alcance")
ANSWERING_REASONS = frozenset({"directa", "parcial"})


@dataclass(frozen=True, slots=True)
class Sentence:
    text: str
    fact_id: str
    source_id: str
    source_field: str


@dataclass(frozen=True, slots=True)
class QuotedPassage:
    quote_id: str
    text: str
    kind: str
    date: str | None
    source_field: str
    truncated: bool = False


@dataclass(slots=True)
class Answer:
    ocid: str
    answerable: bool
    mode: Mode
    reason: Reason
    sentences: list[Sentence] = field(default_factory=list)
    quotes: list[QuotedPassage] = field(default_factory=list)
    note_es: str = ANSWERED_NOTE_ES
    # Counters for telemetry and evaluation; never shown.
    discarded_ids: int = 0
    model_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    grounded: bool | None = None
    cached: bool = False


def fixed_answer(ocid: str, reason: Reason, mode: Mode = MODE_RETRIEVAL) -> Answer:
    return Answer(ocid=ocid, answerable=False, mode=mode, reason=reason, note_es=FIXED_SENTENCES[reason])
