"""Loader and strict validator of the glossary file (`web/src/data/glossary.json`).

The content is written by the web team; the API only serves it. The file is untrusted input: its
size, the number of entries and every string length are capped, control characters are rejected and
terms must be unique. Anything wrong makes the whole file unavailable (`GlossaryUnavailableError`)
rather than serving part of it. Accepted shapes: a list of entries or ``{"items": [...]}``.
"""

from __future__ import annotations

import json
import logging
import threading
import unicodedata
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError, field_validator

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 512 * 1024
MAX_ENTRIES = 400
MAX_ALIASES = 20
_ALLOWED_CONTROL = frozenset("\n")


class GlossaryUnavailableError(Exception):
    """The glossary file is missing, too large or does not have the expected shape."""


def _clean(text: str) -> str:
    if any(unicodedata.category(ch).startswith("C") and ch not in _ALLOWED_CONTROL for ch in text):
        raise ValueError("control characters are not allowed")
    return text


Short = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=100)]


class GlossaryEntry(BaseModel):
    """One term. Unknown keys in the file are ignored; every known key is type- and size-checked."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    term: Short
    aliases: list[Short] = []
    definition_es: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=1500)
    ]
    source: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, max_length=300)] | None = (
        None
    )

    @field_validator("term", "definition_es", "source", mode="after")
    @classmethod
    def _no_control(cls, value: str | None) -> str | None:
        return None if value is None else _clean(value)

    @field_validator("aliases", mode="after")
    @classmethod
    def _aliases(cls, value: list[str]) -> list[str]:
        if len(value) > MAX_ALIASES:
            raise ValueError(f"at most {MAX_ALIASES} aliases")
        for alias in value:
            _clean(alias)
        return value


def parse_glossary(raw: bytes) -> list[dict[str, Any]]:
    """Validated entries as plain dicts, or `GlossaryUnavailableError`."""
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise GlossaryUnavailableError("not valid JSON") from exc
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list) or not 0 < len(items) <= MAX_ENTRIES:
        raise GlossaryUnavailableError("expected a non-empty list of entries within the size cap")
    try:
        entries = [GlossaryEntry.model_validate(item) for item in items]
    except ValidationError as exc:
        raise GlossaryUnavailableError("an entry does not have the expected shape") from exc
    terms = [entry.term.casefold() for entry in entries]
    if len(set(terms)) != len(terms):
        raise GlossaryUnavailableError("duplicate terms")
    return [entry.model_dump() for entry in entries]


class GlossaryStore:
    """Reads the file again only when its modification time or size changes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._stamp: tuple[int, int] | None = None
        self._items: list[dict[str, Any]] = []

    def fingerprint(self) -> str:
        """Identity of the file on disk (modification time and size); used for HTTP validators."""
        try:
            info = self._path.stat()
        except OSError:
            return "missing"
        return f"{info.st_mtime_ns}:{info.st_size}"

    def items(self) -> list[dict[str, Any]]:
        try:
            info = self._path.stat()
        except OSError as exc:
            raise GlossaryUnavailableError("file not found") from exc
        if info.st_size > MAX_FILE_BYTES:
            raise GlossaryUnavailableError("file too large")
        stamp = (info.st_mtime_ns, info.st_size)
        with self._lock:
            if stamp != self._stamp:
                try:
                    self._items = parse_glossary(self._path.read_bytes())
                except OSError as exc:
                    raise GlossaryUnavailableError("file not readable") from exc
                except GlossaryUnavailableError:
                    self._stamp = None
                    raise
                self._stamp = stamp
            return list(self._items)
