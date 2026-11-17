"""Similar-processes response schemas (masked like every other response)."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator

from veedor.domain.masking import PartyFields
from veedor.domain.ocid import is_openable
from veedor.schemas.common import MaskedModel

NOTICE_ES = (
    "La similitud compara el objeto de compra descrito en los datos abiertos. Es una ayuda de búsqueda: "
    "no indica una señal de riesgo ni una acusación."
)


class SimilarProcessOut(MaskedModel):
    party_fields: ClassVar[tuple[PartyFields, ...]] = (("buyer_ruc", "buyer_name", None),)

    ocid: str = Field(examples=["ocds-5wno2w-LICO-GADM-2023-0001"])
    similarity: float = Field(description="Similitud coseno entre -1 y 1 (1 = mismo texto).", examples=[0.87])
    year: int | None = None
    buyer_ruc: str | None = None
    buyer_name: str | None = None
    method: str | None = None
    award_total: float | None = None
    main_cpc: str | None = None
    detail_available: bool = Field(
        True, description="False when the page of this identifier cannot be linked."
    )

    @model_validator(mode="before")
    @classmethod
    def _openable(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("ocid"), str):
            return {**data, "detail_available": is_openable(data["ocid"])}
        return data


class SimilarProcessesOut(BaseModel):
    ocid: str
    k: int
    same_buyer: bool
    items: list[SimilarProcessOut]
    notice_es: str = NOTICE_ES
