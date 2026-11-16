"""Glossary response schema."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GlossaryItem(BaseModel):
    term: str = Field(description="Término.", examples=["Subasta inversa electrónica"])
    aliases: list[str] = Field(
        description="Otras formas de nombrar el término.", examples=[["subasta inversa"]]
    )
    definition_es: str = Field(description="Definición en español claro y neutral.")
    source: str | None = Field(None, description="Fuente de la definición, cuando la hay.")


class Glossary(BaseModel):
    items: list[GlossaryItem]
