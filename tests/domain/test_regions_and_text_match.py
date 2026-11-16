"""Region keys and labels, and the accent/case-insensitive name matching."""

from __future__ import annotations

import pytest

from veedor.domain.regions import (
    PROVINCE_KEYS,
    REGION_KEYS,
    REGION_LABELS,
    SIN_REGION,
    canonical_region,
    is_region_key,
    region_label,
)
from veedor.domain.text_match import ALL_WORDS, PREFIX, SUBSTRING, WORD_START, fold, match_rank


def test_there_are_24_provinces_and_every_key_has_a_label() -> None:
    assert len(PROVINCE_KEYS) == 24 and len(set(REGION_LABELS.values())) == 24
    assert REGION_KEYS == (*PROVINCE_KEYS, SIN_REGION)
    assert all(region_label(key) for key in REGION_KEYS)


@pytest.mark.parametrize(
    ("key", "label"),
    [
        ("LOS RIOS", "Los Ríos"),
        ("SANTO DOMINGO DE LOS TSACHILAS", "Santo Domingo de los Tsáchilas"),
        ("CAÑAR", "Cañar"),
        ("GALAPAGOS", "Galápagos"),
        ("MANABI", "Manabí"),
        ("SUCUMBIOS", "Sucumbíos"),
        ("BOLIVAR", "Bolívar"),
        (SIN_REGION, "Sin provincia registrada"),
    ],
)
def test_labels_are_proper_spanish(key: str, label: str) -> None:
    assert region_label(key) == label


@pytest.mark.parametrize(
    "raw",
    ["MANABI", " manabi ", "Manabí", "MANABÍ", "Manabi\t", "  MANABÍ  "],
)
def test_canonical_region_ignores_case_accents_and_spacing(raw: str) -> None:
    assert canonical_region(raw) == "MANABI"


def test_canonical_region_keeps_the_enye_province_and_collapses_spaces() -> None:
    assert canonical_region("Cañar") == canonical_region("CANAR") == "CAÑAR"
    assert canonical_region("  zamora   chinchipe ") == "ZAMORA CHINCHIPE"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_blank_region_is_sin_region(raw: str | None) -> None:
    assert canonical_region(raw) == SIN_REGION


def test_unknown_region_is_not_guessed() -> None:
    assert canonical_region("ATLANTIDA") is None
    assert not is_region_key("ATLANTIDA") and is_region_key("EL ORO") and is_region_key(SIN_REGION)


def test_fold_removes_accents_case_and_punctuation() -> None:
    assert fold("  Gobierno Municipal ÑANDÚ, S.A. ") == "gobierno municipal nandu s a"


@pytest.mark.parametrize(
    ("name", "query", "rank"),
    [
        ("municipio de cotacachi", "municip", PREFIX),
        ("gad municipal de ejemplo", "municip", WORD_START),
        ("gad municipal de ejemplo", "ejemplo municipal", ALL_WORDS),
        ("gad intermunicipal", "municip", SUBSTRING),
        ("gad municipal", "hospital", None),
        ("gad municipal", "", None),
    ],
)
def test_match_rank_tiers(name: str, query: str, rank: int | None) -> None:
    assert match_rank(name, query) == rank
