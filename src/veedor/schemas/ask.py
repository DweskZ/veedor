"""`POST /processes/{ocid}/ask`: a question about one process and an answer made only of stored evidence."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from veedor.schemas.common import MaskedModel


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        min_length=1,
        max_length=1000,
        description="Una pregunta en español sobre este proceso (3 a 300 caracteres, sin saltos de línea).",
    )


class AskSentence(BaseModel):
    text: str = Field(description="Frase escrita por el sistema a partir de un hecho del proceso.")
    fact_id: str = Field(examples=["process.tenderers"])
    source_id: str = Field(examples=["sercop_ocds"])
    source_field: str = Field(examples=["tender.numberOfTenderers"])


class AskQuote(BaseModel):
    quote_id: str = Field(examples=["q1"])
    text: str = Field(description="Texto publicado por un oferente o por la entidad, tal como se publicó.")
    kind: str = Field(examples=["enquiry_question"])
    date: str | None = None
    source_field: str = Field(examples=["tender.enquiries[3].description"])
    truncated: bool = False


class AskResponse(MaskedModel):
    """Whole-payload masking is the last net: a personal identifier that reached this model is replaced."""

    mask_whole_payload: ClassVar[bool] = True

    ocid: str
    answerable: bool
    mode: Literal["model", "retrieval"] = Field(
        description="model: un modelo eligió los hechos; retrieval: se eligieron por búsqueda, sin modelo."
    )
    reason: str = Field(
        description="answered | no_evidence | judgement | person | instruction | unverified",
        examples=["answered"],
    )
    sentences: list[AskSentence]
    quotes: list[AskQuote]
    note_es: str
