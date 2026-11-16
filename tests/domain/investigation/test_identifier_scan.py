# ruff: noqa: E501
"""The stored-record privacy scan: every spelling of a natural person's identifier is caught."""

from __future__ import annotations

import json

import pytest

from veedor.domain.investigation.identifiers import NON_IDENTIFIER_KEYS, document_has_personal_identifier
from veedor.domain.masking import is_valid_cedula
from veedor.infrastructure.investigations.store import contains_natural_person_ruc

CEDULA = "1710034065"
RUC = CEDULA + "001"
ZW = "​"


def spaced(digits: str, sep: str) -> str:
    return sep.join([digits[:3], digits[3:6], digits[6:9], digits[9:]])


ATTACKS = {
    "plain ruc": RUC,
    "plain cedula": CEDULA,
    "dotted ruc": f"{RUC[:4]}.{RUC[4:7]}.{RUC[7:10]}.{RUC[10:]}",
    "dashed ruc": spaced(RUC, "-"),
    "spaced ruc": spaced(RUC, " "),
    "nbsp ruc": spaced(RUC, " "),
    "dotted cedula": f"{CEDULA[:3]}.{CEDULA[3:6]}.{CEDULA[6:]}",
    "dashed cedula": f"{CEDULA[:9]}-{CEDULA[9]}",
    "spaced cedula": spaced(CEDULA, " "),
    "zero width ruc": ZW.join(RUC),
    "bidi ruc": "‮" + RUC + "‬",
    "fullwidth ruc": "".join(chr(ord(c) + 0xFEE0) for c in RUC),
    "arabic-indic ruc": "".join(chr(0x0660 + int(c)) for c in RUC),
    "arabic-indic cedula": "".join(chr(0x0660 + int(c)) for c in CEDULA),
    "glued after comma": f"a,{RUC}",
    "glued after dot": f"a.{RUC}",
    "glued before letters": f"RUC{RUC}x",
    "followed by digits": RUC + "5",
    "followed by a zero decimal": RUC + ".0",
    "followed by a spaced year": RUC + " 2024",
    "in a sentence": f"Comprador: Juan Perez, C.I. {CEDULA}, quito",
}


@pytest.mark.parametrize("name", ATTACKS)
@pytest.mark.parametrize("shape", ["value", "key", "nested", "list"])
def test_every_spelling_is_caught_in_every_position(name, shape):
    value = ATTACKS[name]
    document = {
        "value": {"buyer": value},
        "key": {value: "x"},
        "nested": {"a": [{"b": {"c": value}}]},
        "list": [1, [value]],
    }[shape]
    assert document_has_personal_identifier(document)
    assert contains_natural_person_ruc(json.dumps(document, ensure_ascii=False))
    assert contains_natural_person_ruc(json.dumps(document))  # \u-escaped too


@pytest.mark.parametrize("value", [int(RUC), int(CEDULA), float(RUC), float(CEDULA)])
def test_json_numbers_are_caught(value):
    assert contains_natural_person_ruc(json.dumps({"x": value}))
    assert contains_natural_person_ruc(json.dumps({"x": [value]}))


def test_the_validator_used_is_the_masking_one():
    assert is_valid_cedula(CEDULA)
    assert not is_valid_cedula("1710034066")


@pytest.mark.parametrize(
    "document",
    [
        {"x": "1790012345001"},  # company
        {"x": "1760001550001"},  # public entity
        {"x": "0992764473001 y 1712*********"},  # company and a masked natural RUC
        {"x": 1234567890123.45},  # float artefact
        {"x": 991.3200000000001},
        {"x": "1234567890123.45"},
        {"x": "1234567890123.4567"},
        {"x": "0.1234567890123"},
        {"x": "991.3200000000001"},
        {"x": "123456.7890123"},
        {"x": "USD 1.234.567.890.123,00"},
        {"x": "USD 1.234.567.890,00"},
        {"x": 1.5e18},
        {"x": float("1e300")},
        {"x": "2026-11-16T10:30:00.123456Z"},
        {"x": "2026-11-16 10:30"},
        {"x": "Contrato 2026-11-16"},
        {"x": "SIE-GADMM-04-2017-20092"},
        {"x": "ocds-5wno2w-R-SIE-GADMM-04-2017-20092"},
        {"x": "CPC 4569012 y 4569012"},
        {"x": "a" * 64},
        {"x": "3f786850e387550fdab836ed7e6dc881de23001b"},  # a hex hash
        {"x": True, "y": None, "z": 12},
        {"x": 1763300000123},  # epoch ms (third digit 6: not natural-person shaped)
        {"x": "0102030405"},  # fails the cédula check
        {"x": "(02) 2 345 678"},
        {"x": ["", {}]},
    ],
)
def test_legitimate_data_stays_clean(document):
    assert not document_has_personal_identifier(document)
    assert not contains_natural_person_ruc(json.dumps(document))


@pytest.mark.parametrize("key", sorted(NON_IDENTIFIER_KEYS))
def test_non_identifier_keys_are_not_scanned(key):
    document = {key: 1740000000001, "inner": {key: 1740000000000}}  # epoch ms, natural-RUC shaped
    assert not document_has_personal_identifier(document)
    assert document_has_personal_identifier({"other": 1740000000001})


def test_a_non_identifier_key_is_still_scanned_as_a_key():
    assert document_has_personal_identifier({RUC: 1})


def test_unparseable_text_is_scanned_raw():
    assert contains_natural_person_ruc(f"not json {RUC}")
    assert not contains_natural_person_ruc("not json 1790012345001")


def test_a_hit_is_a_withheld_record_not_a_crash(tmp_path):
    from datetime import UTC, datetime

    from veedor.domain.investigation.models import InvestigationRecord
    from veedor.infrastructure.investigations.store import InvestigationStore, PersonalDataError

    now = datetime.now(UTC)
    record = InvestigationRecord(
        ocid="x", started_at=now, finished_at=now, renderer_version=1, facts_added=[ZW.join(RUC)]
    )
    with pytest.raises(PersonalDataError):
        InvestigationStore(tmp_path).save(record)


OWN = "ocds-5wno2w-MCBS-EPMR-2019-003-322368"


def test_the_process_own_identifier_is_not_personal_data():
    """Review-4 offline sample: "2019-003-322368" passes the cédula check by chance (2 of 400 records)."""
    assert document_has_personal_identifier({"x": "2019-003-322368"})  # on its own it looks like a cédula
    record = {
        "ocid": OWN,
        "dossier": {"sources": [{"record_id": OWN}], "text": "Código: MCBS-EPMR-2019-003-322368"},
    }
    assert not contains_natural_person_ruc(json.dumps(record))


def test_an_identifier_next_to_the_own_identifier_is_still_caught():
    record = {
        "ocid": OWN,
        "dossier": {"text": f"{OWN} y {RUC}", "other": ["MCBS-EPMR-2019-003-322368", CEDULA]},
    }
    assert contains_natural_person_ruc(json.dumps(record))
    assert not contains_natural_person_ruc(json.dumps({**record, "dossier": {"text": OWN}}))
