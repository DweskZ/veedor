"""Entity-name comparison used to decide whether a Contraloría report concerns the buyer (pure).

Two names refer to the same entity only when their canonical keys are identical. The key removes
accents, case, punctuation and filler words, and rewrites the common variants of a decentralised
government's name ("Gobierno Autónomo Descentralizado Municipal del Cantón X", "GAD Municipal de X",
"Gobierno Municipal de X", "Municipio de X") to one form. Containment and prefix matches are never
accepted: "Ministerio de Educación" is not "Ministerio de Educación Superior". A key shared by two
different buyers in the data is ambiguous and never matches (parish names repeat across provinces).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from veedor.domain.dossier.text import canonical

_FILLER = frozenset({"de", "del", "la", "las", "los", "el", "y", "e", "canton", "cantonal"})
_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bgobierno autonomo descentralizad[oa]s?\b"), "gad"),
    (re.compile(r"\bg\.? ?a\.? ?d\.?(?= )"), "gad"),
    (re.compile(r"\b(?:ilustre )?municipalidad\b"), "gad municipal"),
    (re.compile(r"\bmunicipio\b"), "gad municipal"),
    (re.compile(r"\bgobierno (municipal|provincial|parroquial)\b"), r"gad \1"),
    (re.compile(r"\bgad gad\b"), "gad"),
)
MIN_KEY_CHARS = 4


def canonical_entity_key(name: str | None) -> str | None:
    """Comparison key of an entity name, or None when the name is too short to compare reliably."""
    if not name:
        return None
    text = re.sub(r"[^0-9a-z ]+", " ", canonical(name))
    text = " ".join(text.split())
    for pattern, replacement in _REWRITES:
        text = pattern.sub(replacement, text)
    tokens = [t for t in text.split() if t not in _FILLER]
    key = " ".join(tokens)
    return key if len(key) >= MIN_KEY_CHARS else None


def same_entity(a: str | None, b: str | None) -> bool:
    key_a, key_b = canonical_entity_key(a), canonical_entity_key(b)
    return key_a is not None and key_a == key_b


def build_key_index(buyers: Iterable[tuple[str, str]]) -> dict[str, frozenset[str]]:
    """Map every canonical key to the set of distinct buyer RUCs whose name produces it."""
    index: dict[str, set[str]] = defaultdict(set)
    for ruc, name in buyers:
        key = canonical_entity_key(name)
        if key is not None and ruc:
            index[key].add(ruc)
    return {key: frozenset(rucs) for key, rucs in index.items()}


def is_ambiguous(key: str, index: dict[str, frozenset[str]]) -> bool:
    return len(index.get(key, frozenset())) > 1
