"""Finished investigations stored as one JSON file per process under ``data/investigations/``."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from pathlib import Path

from veedor.domain.investigation.identifiers import text_has_personal_identifier
from veedor.domain.investigation.models import InvestigationRecord

logger = logging.getLogger(__name__)
MAX_OCID_CHARS = 300
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class PersonalDataError(RuntimeError):
    """A record that would have stored a natural person's identifier is refused, not written."""


def valid_ocid(ocid: str) -> bool:
    """Any non-empty identifier without control characters, of bounded length (file names are hashed)."""
    return bool(ocid) and len(ocid) <= MAX_OCID_CHARS and not _CONTROL.search(ocid) and ocid == ocid.strip()


def contains_natural_person_ruc(text: str) -> bool:
    """True when a value or key of the JSON document holds a natural-person RUC or a cédula (any
    spelling: see `veedor.domain.investigation.identifiers`)."""
    return text_has_personal_identifier(text)


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
            record = InvestigationRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            return None  # corrupt entry: treated as absent
        if record.ocid != ocid:  # a file copied under another identifier's hash name
            logger.warning("Stored investigation does not belong to the requested process; ignored")
            return None
        return record

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
