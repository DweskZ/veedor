"""Supplier kind from the third digit of an Ecuadorian RUC."""

from __future__ import annotations

NATURAL_PERSON = "natural_person"
COMPANY = "company"
PUBLIC_ENTITY = "public_entity"
OTHER = "other"
UNKNOWN = "unknown"


def supplier_kind(ruc: str | None) -> str:
    """Return the kind implied by the RUC; "unknown" when the RUC is missing or malformed."""
    if not ruc or len(ruc) != 13 or not ruc.isdigit():
        return UNKNOWN
    digit = ruc[2]
    if digit in "012345":
        return NATURAL_PERSON
    if digit == "9":
        return COMPANY
    if digit == "6":
        return PUBLIC_ENTITY
    return OTHER
