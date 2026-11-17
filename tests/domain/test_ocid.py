"""The identifier pattern accepted in a URL path: a strict allow-list (Finding 8b of review 5)."""

from __future__ import annotations

import re

import pytest

from veedor.domain.ocid import OCID_PATTERN, is_openable

OPENABLE = [
    "ocds-5wno2w-LICO-GADM-2023-0001",
    "ocds-5wno2w-CLC-GAD-MC- 001-2017-91883",  # a space after a hyphen, typed by hand
    "ocds-5wno2w-CLC-GAD MC  002 2016-91883",
    "ocds-5wno2w-CDC-AMASL–001-2016-710584",  # en dash
    "ocds-5wno2w-CDC-GADPRC-002-2020,-110462",
    "ocds-5wno2w-SIE-ÑAÑA-001-2020",
    "ocds-5wno2w-RE (2) 001º-2019",
    "ocds-5wno2w-A:B+C&D",
    "ocds-5wno2w-" + "a" * 120,
]
REFUSED = [
    "ocds-5wno2w-",  # empty code
    "ocds-5wno2w- A",  # starts with a space
    "ocds-5wno2w-" + "a" * 121,
    "ocds-5wno2w-A/B",  # a slash cannot travel in a path segment
    "ocds-5wno2w-A\\B",
    "ocds-5wno2w-../../etc/passwd",
    "ocds-5wno2w-A%2FB",  # percent: no encoded traversal survives
    "ocds-5wno2w-A%00",
    "ocds-5wno2w-A\x00",
    "ocds-5wno2w-A\nB",
    "ocds-5wno2w-A\r",
    "ocds-5wno2w-A\tB",
    "ocds-5wno2w-A\x7f",
    "ocds-5wno2w-A­B",  # soft hyphen (a format character)
    "ocds-5wno2w-A​B",  # zero-width space
    "ocds-5wno2w-A‮B",  # right-to-left override
    "ocds-5wno2w-A'B",
    'ocds-5wno2w-A"B',
    "ocds-5wno2w-A“B”",
    "ocds-5wno2w-A;B",
    "ocds-5wno2w-A?B",
    "ocds-5wno2w-A#B",
    "ocds-5wno2w-A*B",
    "ocds-5wno2w-A|B",
    "ocds-5wno2w-A<B>",
    "ocds-5wno2w-A{B}",
    "ocds-5wno2w-A$B",
    "ocds-5wno2w-x'; SELECT 1; --",
    "ocds-5wno2w-١٢٣",  # Arabic-Indic digits
    "ocds-5wno2w-ＡＢ",  # fullwidth letters
    "ocds-9xxxxx-A",
    "x ocds-5wno2w-A",
]


@pytest.mark.parametrize("ocid", OPENABLE)
def test_hand_typed_codes_with_spaces_and_dashes_are_accepted(ocid: str) -> None:
    assert is_openable(ocid) and re.search(OCID_PATTERN, ocid)


@pytest.mark.parametrize("ocid", REFUSED)
def test_control_characters_slashes_quotes_percent_and_look_alikes_are_refused(ocid: str) -> None:
    assert not is_openable(ocid) and not re.search(OCID_PATTERN, ocid)


def test_the_pattern_is_the_one_the_api_validates_with() -> None:
    from veedor.api.params import OCID_PATTERN as api_pattern

    assert api_pattern == OCID_PATTERN
