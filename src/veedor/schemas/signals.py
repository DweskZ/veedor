"""Signal catalogue schema."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SignalInfo(BaseModel):
    code: str = Field(examples=["SINGLE_BIDDER"])
    label_es: str = Field(examples=["Oferente único"])
    description_es: str
    scope: str
    fields: list[str]
    threshold_rule_es: str
    statistical: bool = Field(description="True when the threshold is derived from the data distribution.")
    needs_registry: bool = Field(description="True when the signal depends on an external registry.")
    kind: str = Field(
        "risk", description="risk | context. Context signals never add to the risk score.", examples=["risk"]
    )
