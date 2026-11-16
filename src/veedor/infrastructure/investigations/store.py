"""Finished investigations stored as one JSON file per process under ``data/investigations/``."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from veedor.domain.investigation.models import InvestigationRecord

MAX_OCID_CHARS = 300
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# A whole-token 13-digit run whose third digit is 0-5 is a natural person's RUC. A '.' or ',' next to
# the digits makes it part of a decimal number (a float artifact, an amount), never an identifier.
_NATURAL_RUC = re.compile(r"(?<![0-9.,*])[0-9]{2}[0-5][0-9]{10}(?![0-9.,]?[0-9])")


class PersonalDataError(RuntimeError):
    """A record that would have stored a natural person's identifier is refused, not written."""


def valid_ocid(ocid: str) -> bool:
    """Any non-empty identifier without control characters, of bounded length (file names are hashed)."""
    return bool(ocid) and len(ocid) <= MAX_OCID_CHARS and not _CONTROL.search(ocid) and ocid == ocid.strip()


def _strings(node: Any):  # noqa: ANN202
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def contains_natural_person_ruc(text: str) -> bool:
    """True when a string value of the JSON document holds a natural person's RUC as a whole token."""
    try:
        document = json.loads(text)
    except ValueError:
        return bool(_NATURAL_RUC.search(text))
    return any(_NATURAL_RUC.search(value) for value in _strings(document))


class InvestigationStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def path(self, ocid: str) -> Path:
        if not valid_ocid(ocid):
            raise ValueError("Invalid ocid")
        digest = hashlib.sha256(ocid.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def save(self, record: InvestigationRecord) -> Path:
        text = record.model_dump_json(indent=2)
        if contains_natural_person_ruc(text):
            raise PersonalDataError(
                f"Refusing to store an investigation of {record.ocid} with a personal RUC"
            )
        path = self.path(record.ocid)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)
        return path

    def load(self, ocid: str) -> InvestigationRecord | None:
        path = self.path(ocid)
        if not path.is_file():
            return None
        try:
            return InvestigationRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            return None  # corrupt entry: treated as absent

    def ocids(self) -> list[str]:
        """Process identifiers of the stored records (read from the records: file names are hashes)."""
        if not self.directory.is_dir():
            return []
        found = []
        for path in self.directory.glob("*.json"):
            try:
                found.append(json.loads(path.read_text(encoding="utf-8"))["ocid"])
            except (ValueError, KeyError, OSError):
                continue
        return sorted(found)
