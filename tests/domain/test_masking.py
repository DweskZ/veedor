from __future__ import annotations

import pytest

from veedor.domain.masking import (
    COMPANY,
    MASKED_NAME,
    NATURAL_PERSON,
    PUBLIC_ENTITY,
    UNKNOWN,
    is_natural_person,
    kind_from_ruc,
    mask_fields,
    mask_party,
    mask_payload,
)

NATURAL = "1712345678001"
COMPANY_RUC = "1790012345001"
PUBLIC = "1760001230001"


@pytest.mark.parametrize("third", "012345")
def test_third_digit_0_to_5_is_natural_person(third: str) -> None:
    assert kind_from_ruc(f"17{third}2345678001") == NATURAL_PERSON


@pytest.mark.parametrize(
    ("ruc", "kind"),
    [
        (COMPANY_RUC, COMPANY),
        (PUBLIC, PUBLIC_ENTITY),
        ("1772345678001", UNKNOWN),
        (None, UNKNOWN),
        ("abc", UNKNOWN),
    ],
)
def test_other_kinds(ruc: str | None, kind: str) -> None:
    assert kind_from_ruc(ruc) == kind


def test_natural_person_is_masked() -> None:
    assert mask_party(NATURAL, "Maria Ficticia", "natural_person") == (
        "1712*********",
        MASKED_NAME,
        NATURAL_PERSON,
    )


def test_company_and_public_entity_are_untouched() -> None:
    assert mask_party(COMPANY_RUC, "Acme S.A.") == (COMPANY_RUC, "Acme S.A.", COMPANY)
    assert mask_party(PUBLIC, "GAD Ejemplo") == (PUBLIC, "GAD Ejemplo", PUBLIC_ENTITY)


def test_kind_hint_masks_even_without_a_ruc() -> None:
    assert mask_party(None, "Maria Ficticia", "natural_person") == (None, MASKED_NAME, NATURAL_PERSON)
    assert is_natural_person(None, "natural_person")


def test_missing_name_stays_missing() -> None:
    assert mask_party(NATURAL, None) == ("1712*********", None, NATURAL_PERSON)


def test_mask_fields_flat_record() -> None:
    row = {
        "winner_ruc": NATURAL,
        "winner_name": "Maria",
        "winner_kind": None,
        "buyer_ruc": PUBLIC,
        "buyer_name": "GAD",
    }
    out = mask_fields(row, (("winner_ruc", "winner_name", "winner_kind"), ("buyer_ruc", "buyer_name", None)))
    assert out["winner_name"] == MASKED_NAME
    assert out["winner_ruc"] == "1712*********"
    assert out["winner_kind"] == NATURAL_PERSON
    assert out["buyer_name"] == "GAD"
    assert row["winner_name"] == "Maria"  # input is not mutated


def test_mask_payload_nested_structures_and_free_text() -> None:
    payload = {
        "winner": {"ruc": NATURAL, "name": "Maria Ficticia Quispe"},
        "tenderers": [
            {"supplier_ruc": NATURAL, "supplier_name": "Maria Ficticia Quispe"},
            {"supplier_ruc": COMPANY_RUC, "supplier_name": "Acme S.A."},
        ],
        "top_suppliers": [{"ruc": "1012345678001", "legal_name": "Pedro Ficticio"}],
        "summary": (
            f"Adjudicado a Maria Ficticia Quispe con RUC {NATURAL}; proveedor Acme S.A. ({COMPANY_RUC})."
        ),
    }
    out = mask_payload(payload)
    text = repr(out)
    assert "Maria" not in text and "Pedro" not in text and NATURAL not in text
    assert out["winner"] == {"ruc": "1712*********", "name": MASKED_NAME}
    assert out["tenderers"][1] == {"supplier_ruc": COMPANY_RUC, "supplier_name": "Acme S.A."}
    assert "Acme S.A." in out["summary"] and COMPANY_RUC in out["summary"]
    assert "[persona natural]" in out["summary"]


def test_mask_payload_masks_unpaired_natural_ruc_in_text() -> None:
    assert mask_payload({"note": f"ruc {NATURAL}"}) == {"note": "ruc 1712*********"}


def test_mask_payload_leaves_scalars_alone() -> None:
    assert mask_payload({"a": 1, "b": None, "c": [1.5, True]}) == {"a": 1, "b": None, "c": [1.5, True]}


# --- free text, parties without a RUC, idempotence

from veedor.domain.masking import (  # noqa: E402
    TEXT_PLACEHOLDER,
    UNIDENTIFIED_NAME,
    is_legal_entity_name,
    is_masked_party,
    is_valid_cedula,
    mask_free_text,
    safe_free_text,
)

VALID_CEDULA = "1710034065"


def test_cedula_check_digit() -> None:
    assert is_valid_cedula(VALID_CEDULA)
    assert not is_valid_cedula("1710034066")  # wrong check digit
    assert not is_valid_cedula("9910034065")  # invalid province
    assert not is_valid_cedula("1790034065")  # third digit >= 6
    assert not is_valid_cedula("17100340")


def test_valid_cedula_is_masked_but_arbitrary_ten_digit_numbers_are_not() -> None:
    assert mask_free_text(f"Cédula {VALID_CEDULA}.") == "Cédula 1710******."
    assert mask_free_text("Contrato número 1234567890 del año") == "Contrato número 1234567890 del año"
    assert mask_free_text(f"Orden {VALID_CEDULA}") == "Orden 1710******"


@pytest.mark.parametrize(
    "prefix", ["CC", "C.C.", "C.I.", "CI:", "CÉDULA", "cedula de identidad", "RUC/PASAPORTE", "CC N°"]
)
def test_ten_digits_after_an_id_keyword_are_masked_even_if_invalid(prefix: str) -> None:
    out = mask_free_text(f"{prefix} 1234567890 fin")
    assert "1234567890" not in out and out.endswith("fin")


def test_natural_ruc_is_masked_company_ruc_is_kept() -> None:
    assert mask_free_text(f"RUC {NATURAL} y {COMPANY_RUC}") == f"RUC 1712********* y {COMPANY_RUC}"


def test_non_ascii_digits_are_not_treated_as_identifiers() -> None:
    assert kind_from_ruc("17١2345678001") == UNKNOWN


def test_known_names_are_masked_case_accent_and_order_insensitive() -> None:
    names = ["Juan Carlos Pérez Mendoza"]
    for text in (
        "a favor de JUAN CARLOS PEREZ MENDOZA para",
        "a favor de pérez mendoza juan carlos para",
        "a favor de Perez Mendoza, Juan para",
        "a favor de Juan Carlos de Perez para",
    ):
        out = mask_free_text(text, names)
        assert TEXT_PLACEHOLDER in out and "erez" not in out and "uan" not in out, text
        assert out.endswith("para")


def test_single_common_word_of_a_name_is_not_masked_alone() -> None:
    assert mask_free_text("Servicio de Juan para la obra", ["Juan Perez"]) == "Servicio de Juan para la obra"


@pytest.mark.parametrize("honorific", ["Sr.", "SRA.", "Dr.", "Ing.", "Arq.", "Ab.", "Lcdo.", "LCDA", "Econ."])
def test_honorific_name_runs_are_masked(honorific: str) -> None:
    out = mask_free_text(f"Asesoría del {honorific} Pedro de la Cruz para el municipio")
    assert "Pedro" not in out and "Cruz" not in out and TEXT_PLACEHOLDER in out


def test_ordinary_text_is_untouched() -> None:
    text = "Construcción de aceras y bordillos en la parroquia Quitumbe, Av. Principal 123"
    assert mask_free_text(text) == text


def test_mask_free_text_is_idempotent() -> None:
    once = mask_free_text(f"Dr. Pedro Salazar CC {VALID_CEDULA} RUC {NATURAL}", ["Pedro Salazar"])
    assert mask_free_text(once, ["Pedro Salazar"]) == once


def test_safe_free_text_withholds() -> None:
    assert safe_free_text("Papelería") == ("Papelería", False)
    assert safe_free_text("Papelería", withhold=True) == (None, True)
    assert safe_free_text("Obra con Ing. Pedro Salazar") == (None, True)
    assert safe_free_text(None) == (None, False)
    assert safe_free_text(None, withhold=True) == (None, True)


@pytest.mark.parametrize(
    "name",
    [
        "CONSTRUCTORA ANDINA S.A.", "ANDES S.A.S.", "TECNO CIA. LTDA.", "SERVICIOS LTDA", "VIAS C.A.",
        "EMPRESA PUBLICA EP", "SERVICIOS E.P.", "CONSORCIO VIAL NORTE", "ASOCIACIÓN DE VECINOS",
        "FUNDACIÓN VIDA", "CORPORACIÓN ANDINA", "COOPERATIVA AHORRO", "COMPAÑÍA DE TRANSPORTE",
        "UNIVERSIDAD AGRARIA", "GAD MUNICIPAL DE EJEMPLO", "GOBIERNO PROVINCIAL", "MUNICIPIO DE QUITO",
        "MINISTERIO DE SALUD", "INSTITUTO NACIONAL", "HOSPITAL GENERAL", "Hospital de Ejemplo",
    ],
)  # fmt: skip
def test_legal_entity_markers(name: str) -> None:
    assert is_legal_entity_name(name)
    assert not is_masked_party(None, name)
    assert mask_party(None, name)[1] == name


@pytest.mark.parametrize(
    "name", ["JUAN PEREZ", "María de los Ángeles Vega", "ANA SANCHEZ", "Pedro", "", None]
)
def test_names_without_marker_are_not_legal_entities(name: str | None) -> None:
    assert not is_legal_entity_name(name)


def test_party_without_ruc_defaults_to_masked() -> None:
    assert mask_party(None, "JUAN PEREZ") == (None, UNIDENTIFIED_NAME, UNKNOWN)
    assert mask_party(None, None) == (None, None, UNKNOWN)
    assert mask_party("0000", "JUAN PEREZ")[1] == UNIDENTIFIED_NAME  # unusable RUC counts as missing


def test_party_masking_is_idempotent() -> None:
    first = mask_party(NATURAL, "Maria", None)
    assert mask_party(*first) == first
    unidentified = mask_party(None, "JUAN PEREZ")
    assert mask_party(*unidentified) == unidentified


def test_mask_payload_masks_party_without_ruc_and_known_names() -> None:
    payload = {
        "winner": {"ruc": None, "name": "JUAN PEREZ"},
        "text": "adjudicado a JUAN PEREZ",
        "entity": {"ruc": None, "name": "ACME S.A."},
    }
    out = mask_payload(payload)
    assert out["winner"]["name"] == UNIDENTIFIED_NAME
    assert out["text"] == f"adjudicado a {TEXT_PLACEHOLDER}"
    assert out["entity"]["name"] == "ACME S.A."
    assert mask_payload(out) == out


def test_mask_payload_accepts_extra_known_names() -> None:
    assert mask_payload({"t": "para Rosa Quito Vega"}, ["Rosa Quito Vega"]) == {
        "t": f"para {TEXT_PLACEHOLDER}"
    }


def test_protected_names_are_not_rewritten_by_the_honorific_rule() -> None:
    hospital = "HOSPITAL DR. GUSTAVO DOMINGUEZ Z."
    text = f"Contrata {hospital} con el Dr. Pedro Salazar"
    out = mask_free_text(text, protected_names=[hospital])
    assert hospital in out and "Salazar" not in out
    assert mask_free_text(f"«{hospital}»", protected_names=[hospital]) == f"«{hospital}»"
    assert "GUSTAVO" not in mask_free_text(hospital)  # without context the rule applies


def test_mask_payload_protects_company_and_buyer_names_in_dicts() -> None:
    payload = {
        "buyer_ruc": "1760001230001",
        "buyer_name": "HOSPITAL DR. LUIS VERA",
        "text": "Compra de HOSPITAL DR. LUIS VERA al Ing. Pedro Salazar",
    }
    out = mask_payload(payload)
    assert out["buyer_name"] == "HOSPITAL DR. LUIS VERA"
    assert "HOSPITAL DR. LUIS VERA" in out["text"] and "Salazar" not in out["text"]


def test_honorifics_can_be_switched_off() -> None:
    assert mask_free_text("Dr. Pedro Salazar", honorifics=False) == "Dr. Pedro Salazar"
