"""Vocabulary that decides which words a quote may contain (pure).

Deny by default: a passage is only shown when every capitalised or ALL-CAPS word it contains is one the data
itself shows to be institutional, geographic, legal or procurement vocabulary, and not a person's name. The
lists are built from the texts, never written by hand:

* ``capitalised``: folded tokens written with a capital (or in capitals) in the *middle* of a sentence of a
  mixed-case passage, in at least ``MIN_PROCESSES`` distinct processes of at least ``MIN_BUYERS`` distinct
  buyers (the name of one official, who signs hundreds of processes of one entity, is not vocabulary; the
  word "Municipal" is written by hundreds of entities), and used far more often than they
  appear in the names of natural persons (``RATIO`` times the number of distinct person names that contain
  them). ``Quito``, ``Municipal``, ``Contratación`` qualify; ``Maria`` or ``Ruales`` do not.
* ``lowercase``: folded tokens written in lower case in at least ``MIN_PROCESSES`` distinct processes under
  the same person-name ratio. They are the ordinary words: the only capitals a sentence may open with, and the
  only words an ALL-CAPS passage may contain (capitals carry no signal there).

A token that is in neither list is *unknown* and a passage that contains it in capitals is not eligible.
Both lists are stored in the ``quote_lexicon`` mart so the API applies the very same function at its
boundary. They hold no name: a token with any weight in person names is excluded by construction.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache

from veedor.domain.dossier.text import canonical

MIN_PROCESSES = 40  # distinct processes in which a form must appear to be vocabulary
MIN_BUYERS = 10  # ... written in the processes of at least this many distinct buyers
RATIO = 20  # appearances (processes) per distinct natural-person name that contains the token
MIN_TOKEN = 2
MIXED_UPPER_SHARE = 0.6
_WORD = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]+")
_SENTENCE_OPENERS = '.!?:;¿¡"«»(-–—*•)'


@lru_cache(maxsize=1_000_000)
def fold(word: str) -> str:
    return canonical(word)


def is_mixed_case(text: str) -> bool:
    """Capitalisation carries information only when the text is not written (mostly) in capitals."""
    letters = [ch for ch in text if ch.isalpha()]
    return len(letters) >= 10 and sum(ch.isupper() for ch in letters) / len(letters) < MIXED_UPPER_SHARE


@dataclass(frozen=True, slots=True)
class Token:
    raw: str
    folded: str
    initial: bool  # opens the text or a sentence, a clause after a colon, a list item

    @property
    def capital(self) -> bool:
        return self.raw[0].isupper()

    @property
    def all_caps(self) -> bool:
        return len(self.raw) >= MIN_TOKEN and self.raw.isupper()


def tokens(text: str) -> Iterator[Token]:
    """Words of `text` with their case and whether they open a sentence."""
    last_end = 0
    first = True
    for match in _WORD.finditer(text):
        gap = text[last_end : match.start()]
        before = gap.rstrip()
        initial = first or (bool(before) and before[-1] in _SENTENCE_OPENERS) or "\n" in gap
        yield Token(match.group(), fold(match.group()), initial)
        last_end = match.end()
        first = False


@dataclass(frozen=True, slots=True)
class Lexicon:
    capitalised: frozenset[str] = frozenset()
    lowercase: frozenset[str] = frozenset()

    def known(self, token: str) -> bool:
        return token in self.capitalised or token in self.lowercase


@dataclass(slots=True)
class FormCounts:
    """Distinct processes in which each folded token appears, by written form."""

    capitalised: Counter[str] = field(default_factory=Counter)
    lowercase: Counter[str] = field(default_factory=Counter)
    capitalised_buyers: Counter[str] = field(default_factory=Counter)  # distinct buyers, capped at MIN_BUYERS
    lowercase_buyers: Counter[str] = field(default_factory=Counter)


def count_forms(rows: Iterable[tuple[str, str, str]]) -> FormCounts:
    """Count, per folded token, the distinct processes (and distinct buyers, up to `MIN_BUYERS`) where it is
    written capitalised (mid-sentence, in a mixed-case passage) and in lower case. `rows` are
    ``(ocid, buyer, text)`` and must be grouped by ocid."""
    counts = FormCounts()
    seen_cap: dict[str, str] = {}
    seen_low: dict[str, str] = {}
    buyers_cap: dict[str, set[str]] = {}
    buyers_low: dict[str, set[str]] = {}
    for ocid, buyer, text in rows:
        mixed = is_mixed_case(text)
        for token in tokens(text):
            if len(token.raw) < MIN_TOKEN:
                continue
            if token.raw[0].islower():
                seen, group, by_form, by_buyer = (
                    seen_low,
                    buyers_low,
                    counts.lowercase,
                    counts.lowercase_buyers,
                )
            elif mixed and not token.initial:
                seen, group, by_form, by_buyer = (
                    seen_cap,
                    buyers_cap,
                    counts.capitalised,
                    counts.capitalised_buyers,
                )
            else:
                continue
            if seen.get(token.folded) != ocid:
                seen[token.folded] = ocid
                by_form[token.folded] += 1
            known = group.setdefault(token.folded, set())
            if len(known) < MIN_BUYERS and buyer not in known:
                known.add(buyer)
                by_buyer[token.folded] = len(known)
    return counts


def person_token_counts(person_names: Iterable[str]) -> Counter[str]:
    """For each folded token, the number of distinct natural-person names that contain it."""
    counts: Counter[str] = Counter()
    for name in set(person_names):
        counts.update({fold(w) for w in _WORD.findall(name) if len(w) >= MIN_TOKEN})
    return counts


def build_lexicon(
    counts: FormCounts,
    persons: Counter[str],
    *,
    min_processes: int = MIN_PROCESSES,
    min_buyers: int = MIN_BUYERS,
    ratio: int = RATIO,
) -> Lexicon:
    def admit(by_form: Counter[str], by_buyer: Counter[str]) -> frozenset[str]:
        return frozenset(
            tok
            for tok, n in by_form.items()
            if n >= min_processes and by_buyer[tok] >= min_buyers and persons.get(tok, 0) * ratio <= n
        )

    return Lexicon(
        admit(counts.capitalised, counts.capitalised_buyers), admit(counts.lowercase, counts.lowercase_buyers)
    )


NAME_MIN_PERSONS = 2  # distinct natural-person names that must contain a token for it to be a name token
NAME_MIN_LENGTH = 3


def build_name_vocabulary(
    counts: FormCounts,
    persons: Counter[str],
    *,
    min_persons: int = NAME_MIN_PERSONS,
    ratio: int = RATIO,
) -> frozenset[str]:
    """Tokens that are names: contained in at least `min_persons` distinct natural-person names and written in
    lower case in fewer than ``ratio * persons`` processes (so ordinary words that are also surnames, such as
    ``luz`` or ``mesa``, stay words). The earlier definition dropped every token that was ever typed in lower
    case more than 2 % of the time, which removed exactly the most common given names and surnames, because
    people type them in lower case ("patricio garcia"); this one is relative to how many persons carry the
    name.
    """
    return frozenset(
        token
        for token, n_persons in persons.items()
        if len(token) >= NAME_MIN_LENGTH
        and n_persons >= min_persons
        and counts.lowercase.get(token, 0) < ratio * n_persons
    )
