"""Errors raised by the dossier layer."""

from __future__ import annotations


class ProcessNotFoundError(LookupError):
    """The requested ocid does not exist in the lake."""

    def __init__(self, ocid: str) -> None:
        super().__init__(f"Process not found: {ocid}")
        self.ocid = ocid


class GroundingError(RuntimeError):
    """Text that failed grounding verification must never be stored; raised instead."""
