"""Deny-by-default screen, lexicon, allegation stems and release-gate rules (synthetic names only)."""

from __future__ import annotations

import pytest

from veedor.domain.quotes.allegation import ALLEGATION_STEMS, allegation_stems, has_allegation_wording
from veedor.domain.quotes.gate import REVIEWER_RULES, rules_hit
from veedor.domain.quotes.lexicon import (
    Lexicon,
    build_lexicon,
    count_forms,
    is_mixed_case,
    person_token_counts,
    tokens,
)
from veedor.domain.quotes.screen import PERSONAL, UNSAFE, check_passage
from veedor.domain.quotes.strict import strict_reason

ORDINARY = (
    "se solicita ampliar el plazo de presentacion de las ofertas y aclarar el valor referencial para la "
    "contratacion de los servicios requeridos por la entidad favor confirmar si podemos presentar los "
    "documentos del proceso hasta la fecha indicada gracias buenos dias estimados por la respuesta las "
    "bases el contrato la oferta el pago los equipos de acuerdo con lo solicitado"
).split()
LEXICON = Lexicon(
    capitalised=frozenset(
        "municipal quito pliegos seccion sercop oferta gad contratacion entidad ecuador servicio sri iva ruc "
        "usd".split()
    ),
    lowercase=frozenset(
        ORDINARY + ["senor", "estimado", "tecnico", "civil", "debe", "presentarse", "empresa", "presenta"]
    ),
)
VOCAB = frozenset({"xavian", "quorlo", "zandrel", "mivenko"})


def reason(text: str, **kw) -> str | None:
    return strict_reason(text, lexicon=LEXICON, name_vocabulary=VOCAB, **kw)


@pytest.mark.parametrize(
    "text",
    [
        "Se solicita ampliar el plazo de presentacion de las ofertas hasta la fecha indicada.",
        "Favor confirmar el valor referencial. Gracias por la respuesta del Servicio.",
        "Pliegos, Seccion 4: la oferta debe presentarse a la entidad.",
        "SE SOLICITA AMPLIAR EL PLAZO DE PRESENTACION DE LAS OFERTAS",
        "El presupuesto es de USD 1.250.000,00 para el contrato del Servicio.",
        "El valor 12345678 corresponde a la oferta; fecha 2023-10-05 y proceso 2023-0145.",
        "La empresa con RUC 1790012345001 presento la oferta.",  # a company RUC
    ],
)
def test_ordinary_institutional_text_is_eligible(text: str) -> None:
    assert reason(text) is None, text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Yo, Xavian Quorlo, en mi calidad de gerente, solicito el plazo.", "self_identification"),
        ("Se solicita el plazo. Atte. Zandrel Mivenko", "sign_off"),
        ("Saludos, se solicita el plazo de la oferta.", "sign_off"),
        ("Se solicita el plazo. F. Zandrel", "sign_off"),
        ("La oferta, representada legalmente por Xavian Quorlo, solicita el plazo.", "self_identification"),
        ("el representante legal solicita el plazo de la oferta", "self_identification"),
        ("el administrador del contrato solicita el plazo", "self_identification"),
        ("Ingeniero Qwerty Asdfgh solicita el plazo.", "title_name"),
        ("Ing. Civil solicita el plazo.", "title_name"),
        ("sr.QUORLO solicita el plazo de la oferta", "title_name"),
        ("el ing. zzyzx solicita el plazo de la oferta", "title_name"),
        ("la licencia profesional 123456-AB corresponde a la oferta", "credential_id"),
        ("el registro senescyt 1234567890 de la oferta", "credential_id"),
        ("cedula de ciudadania 1710034065 de la oferta", "credential_id"),
        ("la placa PBA-1234 del vehiculo de la oferta", "plate"),
        ("el vehiculo ABC 123 de la oferta", "plate"),
        ("INFORMES AL 0995 de la oferta", "long_number"),
        ("llamar al 02 345 6789 para la oferta", "long_number"),
        ("RUC 1710034065001 de la oferta", "long_number"),  # a natural-person RUC
        ("la oferta del paciente indicado", "health_reference"),
        ("la historia clinica de la oferta", "health_reference"),
        ("escribir a alguien@correo.com sobre la oferta", "contact"),
        ("copia de la cedula de zzyzx para la oferta", "credential_id"),
        ("Nombre: zzyzx para la oferta", "labelled_name"),
        ("la oferta de SrPEREZ", "title_name"),
    ],
)
def test_cues_of_a_person_speaking_signing_or_being_identified(text: str, expected: str) -> None:
    assert reason(text) == expected, text


def test_any_capitalised_word_the_data_does_not_show_to_be_institutional_is_refused() -> None:
    assert reason("Se solicita a Zorgonplim ampliar el plazo de la oferta.") == "unknown_capitalised"
    assert reason("Se solicita a Zorgonplim Wuxy ampliar el plazo de la oferta.") == "unknown_capitalised"
    assert (
        reason("Zorgonplim solicita ampliar el plazo de la oferta.") == "unknown_capitalised"
    )  # unknown opener
    assert reason("Se solicita al GAD Municipal de Quito ampliar el plazo de la oferta.") is None
    assert reason("SE SOLICITA A ZORGONPLIM AMPLIAR EL PLAZO") == "caps_unknown_word"
    assert reason("SE SOLICITA AMPLIAR EL PLAZO") is None


def test_two_consecutive_unknown_lowercase_words_are_refused_one_is_not() -> None:
    assert reason("se solicita el plazo de zarquon plixt para la oferta") == "unknown_lowercase_pair"
    assert reason("se solicita el plazo de zarquon para la oferta") is None  # one rare word: a typo or a term
    assert reason("se solicita el plazo de zar plixt para la oferta") is None  # under 4 letters


def test_person_name_vocabulary_matches_in_any_case_and_in_capitals() -> None:
    assert reason("se solicita al xavian ampliar el plazo de la oferta") == "name_token"
    assert reason("SE SOLICITA AL QUORLO AMPLIAR EL PLAZO") == "name_token"


def test_the_names_of_the_process_own_companies_and_entities_are_set_aside() -> None:
    text = "La empresa Zorgonplim Wuxy Cia. Ltda. presenta la oferta."
    assert reason(text) is not None
    assert reason(text, protected_names=["Zorgonplim Wuxy Cia. Ltda."]) is None
    assert reason(text, protected_names=["zorgonplim wuxy cia. ltda."]) is None  # case-insensitive


def test_without_a_lexicon_only_cues_and_vocabulary_apply() -> None:
    assert (
        strict_reason("Zorgonplim solicita el plazo", lexicon=None) is None
    )  # never enough to show a passage
    assert strict_reason("Atte. Zorgonplim", lexicon=None) == "sign_off"


def test_check_passage_uses_the_deny_by_default_screen_after_the_older_ones() -> None:
    verdict = check_passage("Se solicita a Zorgonplim el plazo de la oferta.", lexicon=LEXICON)
    assert (verdict.eligible, verdict.category, verdict.reason) == (
        False,
        PERSONAL,
        "strict_unknown_capitalised",
    )
    assert check_passage("Se solicita el plazo de la oferta.", lexicon=LEXICON).eligible
    unsafe = check_passage("Hubo fraude en la oferta.", lexicon=LEXICON)
    assert unsafe.category == UNSAFE


# --- lexicon ---------------------------------------------------------------------------------------------


def test_tokens_know_sentence_openers_and_case() -> None:
    got = [(t.raw, t.initial) for t in tokens("Se pide: Plazo. Luego la Oferta (SRI)\nNuevo")]
    assert got == [
        ("Se", True), ("pide", False), ("Plazo", True), ("Luego", True), ("la", False), ("Oferta", False),
        ("SRI", True), ("Nuevo", True),
    ]  # fmt: skip
    assert is_mixed_case("Una frase normal con Mayusculas") and not is_mixed_case("TODO EN MAYUSCULAS AQUI")


def test_lexicon_is_built_from_distinct_processes_and_excludes_person_tokens() -> None:
    rows = []
    for i in range(50):
        buyer = f"b{i % 20}"  # 20 distinct buyers
        rows.append((f"p{i}", buyer, "Se pide al Municipal de Quito la oferta. Maria Quorlo firma."))
        rows.append((f"p{i}", buyer, "Se pide al Municipal de Quito la oferta."))  # same process again: once
    for i in range(50):  # a token that one buyer's official signs in 50 processes: not vocabulary
        rows.append((f"q{i}", "b-one", "Se pide al Municipal. Firma Zandrel Mivenko en la oferta."))
    counts = count_forms(rows)
    assert counts.capitalised["municipal"] == 100 and counts.capitalised["quito"] == 50
    assert counts.capitalised["zandrel"] == 50 and counts.capitalised_buyers["zandrel"] == 1
    persons = person_token_counts(
        ["MARIA QUORLO", "MARIA QUORLO", "JOSE QUORLO", "ANA QUORLO", "LUIS QUORLO", "ANA PEREZ"]
    )
    assert persons["quorlo"] == 4 and persons["maria"] == 1  # distinct names, not repetitions
    lexicon = build_lexicon(counts, persons, min_processes=40, ratio=20)
    assert {"municipal", "quito"} <= lexicon.capitalised
    assert "quorlo" not in lexicon.capitalised  # 50 processes but 4 person names (ratio)
    assert persons["maria"] == 1 and "maria" not in lexicon.capitalised  # a person token
    assert "zandrel" not in lexicon.capitalised  # 50 processes but a single buyer
    assert "pide" in lexicon.lowercase and "la" in lexicon.lowercase
    rare = build_lexicon(count_forms([("a", "b", "Se pide al Raro de Quito.")]), persons, min_processes=40)
    assert "raro" not in rare.capitalised  # one process is not vocabulary


# --- allegation stems ------------------------------------------------------------------------------------

POSITIVE = {
    "direccionamiento": [
        "Este proceso esta direccionado.",
        "Hay direccionamiento hacia una empresa.",
        "Estan direccionando",
    ],
    "denuncia": ["Presentare una denuncia ante la entidad.", "Procederemos adenunciar el proceso."],
    "a_dedo": ["Se adjudica a dedo."],
    "sucios_juegos": ["Basta de sucios juegos."],
    "corrup": ["Esto es corrupcion."],
    "no_se_enganen": ["No se engañen con esta oferta."],
    "la_cia_que_todos_sabemos": ["Gana la cía que todos sabemos."],
    "favorec": ["Se favorece a un proveedor."],
    "amanado": ["El proceso fue amañado.", "Un amaño evidente."],
    "colus": ["Existe colusion."],
    "arreglado": ["Todo esta arreglado.", "Es un arreglo previo."],
    "fraud": ["Es un fraude."],
    "ilegal": ["Es ilegal."],
    "irregular": ["Es una situacion irregular."],
    "sobrepreci": ["Hay sobreprecio."],
    "coima": ["Pidieron una coima."],
    "soborn": ["Un soborno."],
    "trampa": ["Es una trampa."],
    "amarrad": ["Esta amarrado el proceso."],
    "a_la_medida": ["Pliegos hechos a la medida.", "Un traje a la medidad de uno."],
    "con_nombre_y_apellido": ["Pliegos con nombre y apellido."],
    "ganador_definido": ["El ganador ya definido.", "ganadores escogidos"],
    "beneficiar_a": ["Para beneficiar a un amigo.", "Con el fin de beneficiar al gobierno."],
    "perjudic": ["Nos perjudica el plazo."],
    "discriminat": ["El requisito es discriminatorio."],
    "sin_transparencia": ["A este proceso le falta transparencia.", "No hay transparencia."],
    "arbitrari": ["Una decision arbitraria."],
    "abusiv": ["Una clausula abusiva.", "Hay abuso de poder."],
    "sospech": ["Es sospechoso."],
    "nepotismo": ["Es nepotismo.", "Hay trafico de influencias."],
    "ladron": ["Son ladrones.", "Una estafa."],
    "beneficiado": ["Son empresas beneficiadas.", "Hay conflicto de intereses.", "Lo que viola la ley."],
}
NEGATIVE = [
    "La dirección de la entidad es la calle principal.",
    "Dirección Administrativa y Financiera.",
    "Las direcciones de entrega se detallan en el anexo.",
    "Luz direccional del vehiculo.",
    "Las luces direccionales y la direccion del tamaño de la pieza, hasta la medida pedida.",
    "Se solicita ampliar el plazo de presentacion de ofertas.",
    "Favor confirmar el valor referencial del presupuesto.",
    "El amanecer del primer dia de plazo.",
    "Los principios de la ley son legalidad, igualdad y transparencia.",
]


def test_every_stem_has_a_positive_example_and_each_example_is_dropped() -> None:
    assert set(POSITIVE) == set(ALLEGATION_STEMS)
    for name, examples in POSITIVE.items():
        for text in examples:
            assert name in allegation_stems(text), (name, text)
            assert has_allegation_wording(text)
            assert not check_passage(text, lexicon=LEXICON).eligible


@pytest.mark.parametrize("text", NEGATIVE)
def test_address_and_department_uses_of_direccion_and_ordinary_text_are_kept(text: str) -> None:
    assert not has_allegation_wording(text), text


def test_matching_is_accent_case_and_lookalike_insensitive() -> None:
    assert has_allegation_wording("DIRECCIÓN-AMIENTO".replace("-", ""))
    assert has_allegation_wording("Direccionаdo")  # Cyrillic a
    assert has_allegation_wording("A DEDO")


# --- release gate ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("Ingeniero Qwerty Asdfgh solicita", "r1_title_then_name"),
        ("representada legalmente por Qwerty Asdfgh Zxcvb", "r2_role_then_name"),
        ("se solicita al ing Qwerty", "r3_honorific_then_capitalised"),
        ("Atentamente, el equipo", "r4_sign_off_or_first_person"),
        ("el vehiculo PBA-1234", "r5_vehicle_plate"),
        ("llamar al 02 345 6789", "r6_telephone"),
        ("registro senescyt 1234-5678", "r7_identity_document_word"),
        ("sr.QUORLO", "o1_glued_honorific"),
        ("INFORMES AL 0995", "o2_partial_mobile"),
        ("escribir a alguien@correo.com", "o3_email"),
        ("la paciente indicada", "o7_health"),
        ("es un fraude", "o9_accusation_stem"),
    ],
)
def test_gate_rules_catch_what_they_are_for(text: str, rule: str) -> None:
    assert rule in rules_hit(text), (text, rules_hit(text))


def test_gate_has_the_seven_reviewer_rules_and_is_silent_on_clean_text() -> None:
    assert len(REVIEWER_RULES) == 7
    assert rules_hit("Se solicita ampliar el plazo de presentacion de las ofertas del Servicio.") == []
    assert rules_hit("El presupuesto es de USD 1.250.000,00 y el proceso 2023-0145.") == []


def test_everything_the_screen_accepts_passes_the_gate() -> None:
    accepted = [
        "Se solicita ampliar el plazo de presentacion de las ofertas hasta la fecha indicada.",
        "SE SOLICITA AMPLIAR EL PLAZO DE PRESENTACION DE LAS OFERTAS",
        "El valor 12345678 corresponde a la oferta; fecha 2023-10-05.",
        "La empresa con RUC 1790012345001 presento la oferta.",
    ]
    for text in accepted:
        assert check_passage(text, lexicon=LEXICON, name_vocabulary=VOCAB).eligible, text
        assert rules_hit(text) == [], (text, rules_hit(text))


def test_the_cedula_of_the_document_type_and_the_word_sr_inside_other_words_are_not_cues() -> None:
    for text in (
        "se presenta copia de cedula de identidad con la oferta",
        "la cedula de ciudadania del representante se adjunta a la oferta",
        "SE INGRESA EL DRENAJE POR SRES",
    ):
        got = reason(text)
        assert got != "credential_id" and got != "title_name", (text, got)


def test_the_screen_refuses_everything_the_release_gate_would_flag() -> None:
    """The gate rules are part of the screen: a mart built by `check_passage` cannot fail the gate."""
    for text in (
        "Se solicita ampliar el plazo del Ingeniero Qwerty Asdfgh de la oferta",
        "llamar al 02 345 6789 por la oferta",
        "la oferta del PBA-1234",
    ):
        verdict = check_passage(text, lexicon=LEXICON)
        assert not verdict.eligible, text
        assert rules_hit(text)
