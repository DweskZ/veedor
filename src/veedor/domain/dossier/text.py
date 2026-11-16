"""Text normalisation shared by the template and the grounding verifier (pure)."""

from __future__ import annotations

import re
import unicodedata


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def fold_chars(text: str) -> str:
    """Lowercase and strip accents character by character, so offsets stay aligned with `text`."""
    out: list[str] = []
    for ch in text:
        base = unicodedata.normalize("NFD", ch)[0]
        out.append(base.casefold() if len(base.casefold()) == 1 else base)
    return "".join(out)


def norm(text: str) -> str:
    """Comparison key: accents stripped, case folded, punctuation collapsed to single spaces."""
    return " ".join(re.sub(r"[^0-9a-z]+", " ", strip_accents(text).casefold()).split())


def pad(normalised: str) -> str:
    return f" {normalised} "


def collapse_spaces(text: str) -> str:
    return " ".join(text.split())


# Cyrillic and Greek letters that look like Latin ones. Mapped before wording checks so that
# "frаude" (Cyrillic а) is read as "fraude".
CONFUSABLES = str.maketrans(
    "аеорсхуіјѕԁԛԝАВЕКМНОРСТХαεινκορτυχΑΒΕΖΗΙΚΜΝΟΡΤΥΧ",
    "aeopcxyijsdqwABEKMHOPCTXaeivkoptuxABEZHIKMNOPTYX",
)


def canonical(text: str) -> str:
    """NFKC, hidden characters removed, look-alike letters mapped to Latin, accents stripped, lowercase."""
    import re

    stripped = re.sub("[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]", "", text)
    return fold_chars(unicodedata.normalize("NFKC", stripped).translate(CONFUSABLES))
