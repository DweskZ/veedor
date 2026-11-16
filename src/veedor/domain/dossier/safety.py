"""Heuristic screen for untrusted free text before it is reproduced in a dossier (pure).

Source text (descriptions, activities, evidence strings) is only ever shown as a verbatim quote. If it
contains forbidden wording, a link or instruction-like phrasing it is not reproduced at all. This is
defence in depth: the grounding verifier remains the primary control.
"""

from __future__ import annotations

import re

from veedor.domain.dossier.text import canonical
from veedor.domain.dossier.vocabulary import (
    FORBIDDEN_PATTERN,
    HIDDEN_CHARS,
    INFERENCE_PATTERN,
    MARKUP,
    NON_LATIN_LETTERS,
)

_LINK = re.compile(r"https?://|ftp://|www\.|mailto:|\b[\w-]+\.(?:com|net|org|ec|io)\b")
_INSTRUCTION = re.compile(
    r"\b(?:ignor\w+|olvid\w+|instruccion\w*|system prompt|sistema:|prompt|declara|declare|responde|"
    r"actua como|act as|ignore|disregard|previous instructions|jailbreak|revela\w*|reveal)\b"
    r"|</?\w*(?:datos|system|instruc)\w*>"
)


def is_unsafe_text(text: str) -> bool:
    folded = canonical(text)
    return bool(
        FORBIDDEN_PATTERN.search(folded)
        or INFERENCE_PATTERN.search(folded)
        or _LINK.search(folded)
        or _INSTRUCTION.search(folded)
        or HIDDEN_CHARS.search(text)
        or NON_LATIN_LETTERS.search(text)
        or MARKUP.search(text)
    )
