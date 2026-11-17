"""A name-like pair of words in a passage, from a vocabulary of person-name tokens (pure).

NOTE (review 5): the production vocabulary is now built by `domain.quotes.lexicon.build_name_vocabulary`
(relative to how many natural-person names carry a token, and applied in any case by `domain.quotes.strict`).
`build_vocabulary` below drops every token that is ever typed in lower case more than 2 % of the time, which
removed the commonest given names and surnames; it is kept for its tests and for `probable_person_name`.

The masking heuristic only knows the names of the parties of a process. A passage can also name a person
who is not a party (a technician proposed by a bidder, an official). Such a person usually appears with
two or more consecutive capitalised words that are given names or surnames ("HECTOR IVAN BAQUERIZO").

The vocabulary is built from the names of the natural persons found in the data itself:

* tokens that occur in at least `MIN_PERSONS` (2) distinct natural-person names;
* of at least `MIN_LENGTH` letters;
* that are not ordinary Spanish words: a token that also appears in lower case in the texts (``cruz``,
  ``luz``, ``flores``) is dropped, so a name that is also a noun does not make every sentence suspicious.

A passage is *probably naming a person* when two consecutive capitalised words are both in the vocabulary.
Names inside the process's own protected names (the buyer, the companies) are ignored. The rule is a
net with false positives (hospitals and streets named after people) and false negatives (rare names,
names written in lower case): it complements the party-name masking and never replaces it.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping

from veedor.domain.dossier.text import canonical

MIN_PERSONS = 2
MIN_LENGTH = 4
MAX_LOWERCASE_SHARE = 0.02
_WORD = re.compile(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+")
_PLAIN = re.compile(r"[a-z]+")


def fold(word: str) -> str:
    return canonical(word)


def build_vocabulary(
    person_names: Iterable[str],
    lowercase_counts: Mapping[str, int],
    capitalised_counts: Mapping[str, int],
    *,
    min_persons: int = MIN_PERSONS,
) -> frozenset[str]:
    """Tokens of natural-person names, minus the ones the texts also use as ordinary words."""
    persons: Counter[str] = Counter()
    for name in person_names:
        persons.update({t for t in _PLAIN.findall(fold(name)) if len(t) >= MIN_LENGTH})
    return frozenset(
        token
        for token, count in persons.items()
        if count >= min_persons
        and lowercase_counts.get(token, 0)
        <= MAX_LOWERCASE_SHARE * (lowercase_counts.get(token, 0) + capitalised_counts.get(token, 0) + 1)
    )


def word_case_counts(texts: Iterable[str]) -> tuple[Counter[str], Counter[str]]:
    """How often each folded word is written in lower case and capitalised in the given texts."""
    lower: Counter[str] = Counter()
    capital: Counter[str] = Counter()
    for text in texts:
        for word in _WORD.findall(text):
            (lower if word[0].islower() else capital)[fold(word)] += 1
    return lower, capital


def probable_person_name(text: str, vocabulary: frozenset[str], protected_names: Iterable[str] = ()) -> bool:
    """True when two consecutive capitalised words of `text` are both person-name tokens."""
    if not vocabulary:
        return False
    for name in protected_names:  # a protected name is replaced by a break so it never forms a pair
        if len(name.strip()) >= 3:
            text = re.sub(re.escape(name.strip()), " | ", text, flags=re.IGNORECASE)
    previous: str | None = None
    for match in re.finditer(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+|[^\sA-Za-zÁÉÍÓÚÑáéíóúñ]+", text):
        word = match.group()
        if not word[0].isalpha() or not word[0].isupper():
            previous = None
            continue
        token = fold(word)
        if token in vocabulary:
            if previous is not None:
                return True
            previous = token
        else:
            previous = None
    return False
