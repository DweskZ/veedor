"""Canonical region keys and display labels (pure, no I/O).

``buyer_region`` in the lake holds the province of the BUYING entity as an upper-case Spanish name
without accents except the letter Ñ (``CAÑAR``), or NULL. This module is the single mapping from
those values to a stable key and a proper Spanish label. Matching is defensive: surrounding and
repeated whitespace, letter case and accents are ignored, so ``" Los Ríos "`` and ``"LOS RIOS"``
are the same province.
"""

from __future__ import annotations

import re
import unicodedata

SIN_REGION = "SIN_REGION"
SIN_REGION_LABEL = "Sin provincia registrada"
NATIONAL = "NACIONAL"
NATIONAL_LABEL = "Nacional"

# Canonical key (as stored in the lake) -> display label.
REGION_LABELS: dict[str, str] = {
    "AZUAY": "Azuay",
    "BOLIVAR": "Bolívar",
    "CARCHI": "Carchi",
    "CAÑAR": "Cañar",
    "CHIMBORAZO": "Chimborazo",
    "COTOPAXI": "Cotopaxi",
    "EL ORO": "El Oro",
    "ESMERALDAS": "Esmeraldas",
    "GALAPAGOS": "Galápagos",
    "GUAYAS": "Guayas",
    "IMBABURA": "Imbabura",
    "LOJA": "Loja",
    "LOS RIOS": "Los Ríos",
    "MANABI": "Manabí",
    "MORONA SANTIAGO": "Morona Santiago",
    "NAPO": "Napo",
    "ORELLANA": "Orellana",
    "PASTAZA": "Pastaza",
    "PICHINCHA": "Pichincha",
    "SANTA ELENA": "Santa Elena",
    "SANTO DOMINGO DE LOS TSACHILAS": "Santo Domingo de los Tsáchilas",
    "SUCUMBIOS": "Sucumbíos",
    "TUNGURAHUA": "Tungurahua",
    "ZAMORA CHINCHIPE": "Zamora Chinchipe",
}
PROVINCE_KEYS: tuple[str, ...] = tuple(REGION_LABELS)
REGION_KEYS: tuple[str, ...] = (*PROVINCE_KEYS, SIN_REGION)
_LABELS = {**REGION_LABELS, SIN_REGION: SIN_REGION_LABEL}

_WHITESPACE = re.compile(r"\s+")


def _fold(text: str) -> str:
    """Upper case, accents removed (including the tilde of Ñ), whitespace collapsed."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WHITESPACE.sub(" ", stripped).strip().upper()


_BY_FOLDED = {_fold(key): key for key in PROVINCE_KEYS}


def canonical_region(raw: str | None) -> str | None:
    """Canonical key for a raw ``buyer_region`` value.

    ``SIN_REGION`` for NULL or blank, the province key for a recognised value (whatever its case,
    accents or spacing), ``None`` for a non-blank value that is not a known province.
    """
    if raw is None or not raw.strip():
        return SIN_REGION
    return _BY_FOLDED.get(_fold(raw))


def region_label(key: str) -> str:
    """Display label of a canonical key (``SIN_REGION`` included)."""
    return _LABELS[key]


def is_region_key(value: str) -> bool:
    return value in _LABELS
