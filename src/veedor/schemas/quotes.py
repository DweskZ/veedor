"""Quotes of a process: text written by bidders or the buying entity, shown as published."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from veedor.schemas.common import MaskedModel

QUOTES_NOTE_ES = (
    "Estas citas son texto escrito por oferentes o por la entidad contratante, mostrado tal como se publicó. "
    "No son palabras de Veedor ni constituyen una afirmación sobre el proceso. Provienen del registro "
    "publicado del proceso (preguntas, respuestas y textos de adjudicación), no de los documentos del "
    "proceso. La relación con la señal se estima por similitud de significado y puede ser inexacta."
)


class QuotePair(BaseModel):
    kind: str = Field(examples=["enquiry_answer"])
    text: str
    source_field: str = Field(examples=["tender.enquiries[3].answer"])
    truncated: bool = Field(default=False, description="The paired passage is shown cut.")


class QuoteItem(BaseModel):
    kind: str = Field(
        description="enquiry_question | enquiry_answer | award_text", examples=["enquiry_question"]
    )
    text: str
    date: str | None = None
    author_kind: str = Field(description="oferente | entidad", examples=["oferente"])
    source_field: str = Field(examples=["tender.enquiries[3].description"])
    related_signal: str = Field(examples=["SHORT_TENDER_WINDOW"])
    related_signal_label_es: str | None = None
    similarity: float = Field(description="Coseno entre el pasaje y el tema de la señal (-1 a 1).")
    truncated: bool = Field(default=False, description="The main passage (not the pair) is shown cut.")
    pair: QuotePair | None = None


class QuotesOmitted(BaseModel):
    personal_data: int = 0
    unsafe: int = 0
    below_relevance: int = 0


class ProcessQuotes(MaskedModel):
    """Whole-payload masking is the last net: a personal identifier that reached this model is replaced."""

    mask_whole_payload: ClassVar[bool] = True

    ocid: str
    items: list[QuoteItem]
    available_total: int
    omitted: QuotesOmitted
    note_es: str = QUOTES_NOTE_ES
