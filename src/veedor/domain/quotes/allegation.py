"""Accusation-like wording written by third parties (pure).

The dossier layer's unsafe screen refuses Veedor's own accusation vocabulary. Bidders and entities also write
hostile or accusing text in enquiries ("direccionado", "a dedo", "sucios juegos", "la cía que todos
sabemos"), and a quote that appears beside a risk signal reads as if Veedor agreed with it. These stems
make such passages ineligible. Matching is on `canonical` text (accents, case and look-alikes folded), on word
beginnings for stems and on whole words for the ambiguous ones.

"dirección" (an address, a department) is common and harmless; only the verb family ("direccionado",
"direccionamiento", "direccionando", "direcciona") in the sense of steering a contract is refused, and it
is matched by suffix ("direccionar", "direccionado", "direccionamiento", "redireccionar") so that "dirección",
"direcciones" and "direccional" are untouched.
"""

from __future__ import annotations

import re

from veedor.domain.dossier.text import canonical

# name -> pattern on canonical (lower-case, accent-free) text. The name is the counter label.
ALLEGATION_STEMS: dict[str, str] = {
    "direccionamiento": r"direccion(?:a\b|ar\b|an\b|aron\b|aria|aran|ara\b|ado|ada|amiento|ando)",
    "denuncia": r"denunci",
    "a_dedo": r"\ba dedo\b",
    "sucios_juegos": r"\bsucios? juegos?\b",
    "corrup": r"\bcorrup",
    "no_se_enganen": r"\bno se enganen\b",
    "la_cia_que_todos_sabemos": r"\bla (?:cia|compania|empresa)\b[^.]{0,20}\bque todos sabemos\b",
    "favorec": r"\bfavorec",
    "amanado": r"\baman(?:ad[oa]s?|ar|aron|ando|os?\b|an\b)",
    "colus": r"\bcolus",
    "arreglado": r"\barregl(?:ado|ada|ados|adas|o)\b",
    "fraud": r"\bfraud",
    "ilegal": r"\bilegal",
    "irregular": r"\birregular",
    "sobrepreci": r"\bsobrepreci",
    "coima": r"\bcoima",
    "soborn": r"\bsoborn",
    "trampa": r"\btrampa",
    "amarrad": r"\bamarrad",
    "a_la_medida": r"\ba la medida",
    "con_nombre_y_apellido": r"\bcon nombre y apellido",
    "ganador_definido": r"\bganador(?:es)? (?:ya )?(?:definido|elegido|escogido)",
    "beneficiar_a": r"\bbeneficiar a",
    "perjudic": r"\bperjudic",
    # Added after reading 30 kept passages near the boundary and 100 passages beside single-bidder and
    # recurring-co-bidder signals (docs/REVIEWS.md, review 5): hostile wording the reviewer's list missed.
    "discriminat": r"\bdiscriminat",
    "sin_transparencia": (
        r"\b(?:falta(?:n)?(?: de)? transparencia|sin transparencia|poca transparencia|"
        r"no (?:hay|existe|es) transparen)"
    ),
    "arbitrari": r"\barbitrari",
    "abusiv": r"\babusiv|\babuso de\b",
    "sospech": r"\bsospech",
    "nepotismo": r"\bnepotism|\bfavoritism|\btrafico de influencias",
    "beneficiado": (
        r"\bbeneficiad[oa]s?\b|\bconflicto de intereses\b|"
        r"\bviola(?:n|ndo|cion|ciones)? (?:la|el|los|las)\b"
    ),
    "ladron": r"\bladron|\bestaf(?:a|ad|ador)",
}
_COMPILED = {name: re.compile(pattern) for name, pattern in ALLEGATION_STEMS.items()}


def allegation_stems(text: str) -> list[str]:
    """Names of the stems found in `text` (empty when there is none)."""
    canon = canonical(text)
    return [name for name, pattern in _COMPILED.items() if pattern.search(canon)]


def has_allegation_wording(text: str) -> bool:
    canon = canonical(text)
    return any(pattern.search(canon) for pattern in _COMPILED.values())
