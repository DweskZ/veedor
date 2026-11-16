"""Human review of a process: record a decision and list the history."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from veedor.domain.dossier.text import canonical
from veedor.domain.dossier.vocabulary import FORBIDDEN_PATTERN
from veedor.domain.masking import mask_free_text
from veedor.use_cases.queries.ports import NotFoundError


class ReviewStoreUnavailableError(Exception):
    """The review store cannot be reached or is not migrated."""


class ReviewsDisabledError(Exception):
    """Writing reviews is switched off (flag off or no token configured)."""


class ReviewAuthError(Exception):
    """Missing or wrong bearer token."""


class ForbiddenWordingError(ValueError):
    """The text asserts wrongdoing, which Veedor never states."""

    def __init__(self, terms: list[str]) -> None:
        self.terms = terms
        super().__init__("The text uses wording that asserts wrongdoing: " + ", ".join(terms))


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    id: int
    ocid: str
    status: str
    note: str | None
    reviewer: str | None
    created_at: datetime


class ReviewRepository(Protocol):
    def add(self, ocid: str, status: str, note: str | None, reviewer: str | None) -> ReviewRecord: ...

    def list_for(self, ocid: str) -> list[ReviewRecord]: ...


def strip_control_chars(text: str) -> str:
    """Remove control and format characters (NUL included); keep newlines and tabs."""
    return "".join(
        ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in {"Cc", "Cf", "Cs", "Co", "Cn"}
    )


# Digit and symbol look-alikes ("fr4ude", "c0rrupto") on top of the dossier's canonical form, which
# already handles case, accents, fullwidth, combining and hidden characters and Cyrillic/Greek letters.
_LEET = str.maketrans("013457@$", "oieastas")
# Verb forms the dossier vocabulary does not list yet ("robaron", "hurtaron").
_EXTRA_FORBIDDEN = re.compile(r"\b(?:rob(?:ar|aron|aba\w*|ad[oa]s?)|hurt(?:ar|aron|o|ado))\b")


def find_forbidden_terms(text: str) -> list[str]:
    """Wording that asserts wrongdoing, using the dossier verifier's canonical form and vocabulary."""
    canon = canonical(text)
    found: set[str] = set()
    for candidate in (canon, canon.translate(_LEET)):
        found.update(m.group() for m in FORBIDDEN_PATTERN.finditer(candidate))
        found.update(m.group() for m in _EXTRA_FORBIDDEN.finditer(candidate))
    return sorted(found)


def clean_review_text(
    text: str | None, person_names: Sequence[str] = (), protected_names: Sequence[str] = ()
) -> str | None:
    """Sanitise, reject wording that asserts wrongdoing, and mask personal data before storing."""
    stripped = strip_control_chars(text or "").strip()
    if not stripped:
        return None
    if terms := find_forbidden_terms(stripped):
        raise ForbiddenWordingError(terms)
    return mask_free_text(stripped, person_names, protected_names)


class ReviewService:
    def __init__(
        self,
        repository: ReviewRepository,
        process_exists: Callable[[str], bool],
        name_context: Callable[[str], tuple[list[str], list[str]]] = lambda ocid: ([], []),
    ) -> None:
        self._repository = repository
        self._process_exists = process_exists
        self._name_context = name_context

    def submit(self, ocid: str, status: str, note: str | None, reviewer: str | None) -> ReviewRecord:
        if not self._process_exists(ocid):
            raise NotFoundError("process", ocid)
        persons, protected = self._name_context(ocid)
        clean_note = clean_review_text(note, persons, protected)
        clean_reviewer = clean_review_text(reviewer, persons, protected)
        return self._repository.add(ocid, status, clean_note, clean_reviewer)

    def history(self, ocid: str) -> list[ReviewRecord]:
        return self._repository.list_for(ocid)
