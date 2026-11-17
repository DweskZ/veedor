"""How close a question is to the retrieval key phrases (pure).

Used to show that the unseen phrasings are independent of `domain.qa.facts.FACT_KEYS_ES`: content words are
folded (accents, case), cut to a five-letter stem (so "adjudico" and "adjudicado" match) and compared with
the Jaccard index against each key phrase; the nearest phrase decides.
"""

from __future__ import annotations

import re

from veedor.domain.dossier.text import canonical
from veedor.domain.qa.facts import FACT_KEYS_ES

STEM = 5
STOPWORDS = frozenset(
    "a al algo ante aqui con cual cuales de del el ella en es esa ese eso esta este esto la las le les lo "
    "los "
    "me mi mis no o para por que se si sin su sus un una uno unos y ya como hay ha han fue son ser".split()
)
_SIGNAL_KEYS = ("por que tiene esta senal", "que significa la senal", "senal de riesgo")


def content_stems(text: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", canonical(text))
    return frozenset(w[:STEM] for w in words if w not in STOPWORDS and len(w) >= 2)


def key_phrases() -> list[str]:
    """Every retrieval key phrase (folded) of the fact catalogue plus the signal key phrases."""
    phrases = [canonical(p).strip() for keys in FACT_KEYS_ES.values() for p in keys.split(";")]
    return [p for p in phrases if p] + list(_SIGNAL_KEYS)


def folded(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", canonical(text)))


def nearest_overlap(text: str, phrases: list[str] | None = None) -> tuple[float, str]:
    """``(Jaccard of content stems, key phrase)`` of the nearest key phrase."""
    mine = content_stems(text)
    best, best_phrase = 0.0, ""
    for phrase in phrases or key_phrases():
        theirs = content_stems(phrase)
        union = mine | theirs
        score = len(mine & theirs) / len(union) if union else 0.0
        if score > best:
            best, best_phrase = score, phrase
    return best, best_phrase


def equals_or_contains(text: str, phrases: list[str] | None = None) -> str | None:
    """A key phrase that equals the question, is contained in it or contains it (folded, on word borders)."""
    q = f" {folded(text)} "
    for phrase in phrases or key_phrases():
        p = f" {folded(phrase)} "
        if p in q or q in p:
            return phrase
    return None
