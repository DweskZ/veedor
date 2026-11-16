"""Cases an independent review showed passing the verifier. Each must be rejected."""

import pytest

from veedor.domain.dossier.grounding import verify

HOMOGLYPH = "El proveedor cometiо fraude."  # Cyrillic o
ADVERSARIAL = [
    # accusation vocabulary and synonyms
    *[
        f"Los indicadores muestran {word} en este proceso."
        for word in (
            "amañado",
            "direccionado",
            "testaferro",
            "lavado de activos",
            "defraudación",
            "prevaricato",
            "cohecho",
            "coima",
            "soborno",
            "sobreprecio",
            "cartel",
            "nepotismo",
            "colusión",
            "empresa de papel",
            "acuerdo previo",
            "corrupción",
            "malversación",
        )
    ],
    "El proveedor favoreció indebidamente a la entidad.",
    # Unicode evasions
    "El proveedor cometió frau​de.",
    "El proveedor cometió fr‮aude.",
    HOMOGLYPH,
    "El proveedor cometió ｆｒａｕｄｅ.",
    "El proveedor cometió fraυde.",  # Greek upsilon
    # unsupported claims, with and without figures
    "Por lo tanto se concluye que el proceso es atípico.",
    "El monto supera con creces el presupuesto.",
    "Esto demuestra que hubo un trato especial.",
    "El proceso no tuvo un solo oferente.",
    "El proceso recibió un solo oferente en su fase final.",  # fixture has 1 tenderer; see below
    # wrong dates, wrong nouns
    "Se adjudicó el 2023-05-22.",
    "Se adjudicó el 22 de mayo de 2023.",
    "El proveedor inició actividades el 25 de agosto de 2023.",
    "El proceso tuvo 2023 oferentes.",
    "El proveedor tiene 95 años.",
    "La entidad registra 2023 adjudicaciones previas.",
    # roles
    "El proveedor adjudicado es HOSPITAL GENERAL DE EJEMPLO.",
    "La entidad contratante es COMERCIAL ANDES S.A.",
    "Proveedor adjudicado: constructora andina sa.",
    "El proveedor adjudicado es una empresa que cambió de nombre.",
    # markup
    "<script>alert(1)</script>",
    "Ver [detalle](javascript:alert(1)) del proceso.",
    "Consulte <b>el proceso</b> ahora.",
]
# The single-bidder positive claim is true for the fixture; it must pass, so it is kept apart below.
ADVERSARIAL = [t for t in ADVERSARIAL if t != "El proceso recibió un solo oferente en su fase final."]


@pytest.mark.parametrize("text", ADVERSARIAL)
def test_adversarial_text_is_rejected(text, full_pack):
    full_pack = full_pack.model_copy(
        update={"process": full_pack.process.model_copy(update={"n_tenderers": 1})}
    )
    report = verify(text, full_pack)
    assert not report.passed, text


def test_negated_single_bidder_is_rejected_only_when_it_contradicts_the_evidence(full_pack):
    one = full_pack.model_copy(update={"process": full_pack.process.model_copy(update={"n_tenderers": 1})})
    many = full_pack.model_copy(update={"process": full_pack.process.model_copy(update={"n_tenderers": 4})})
    assert not verify("El proceso no tuvo un solo oferente.", one).passed
    assert verify("El proceso no tuvo un solo oferente.", many).passed
    assert verify("El proceso recibió un solo oferente.", one).passed
    assert not verify("El proceso recibió un solo oferente.", many).passed
    assert verify("La proporción de procesos con un solo oferente es 12,3 %.", many).passed


def test_legitimate_phrases_still_pass(full_pack):
    ok = [
        "El proveedor adjudicado es COMERCIAL ANDES S.A.",
        "La entidad contratante es HOSPITAL GENERAL DE EJEMPLO.",
        "Proveedor adjudicado: no disponible.",
        "El proceso tuvo 1 oferente.",
        "La entidad registra 3 adjudicaciones previas.",
        "El proveedor inició actividades el 22 de mayo de 2023.",
    ]
    for text in ok:
        report = verify(text, full_pack)
        assert report.passed, (text, [t.model_dump() for t in report.unsupported + report.forbidden])


# Entity and place names from the data are verified spans ------------------------------------
@pytest.mark.parametrize(
    "buyer",
    [
        "UNIDAD DE INVESTIGACIONES DE DELITOS CONTRA LA VIDA",
        "COMISIÓN METROPOLITANA DE LUCHA CONTRA LA CORRUPCIÓN",
        "GAD PARROQUIAL TRES DE NOVIEMBRE",
        "GAD MUNICIPAL DIEZ DE AGOSTO",
    ],
)
def test_names_with_forbidden_or_number_words_pass_only_as_exact_spans(buyer, full_pack):
    pack = full_pack.model_copy(
        update={"process": full_pack.process.model_copy(update={"buyer_name": buyer})}
    )
    assert verify(f"La entidad contratante es {buyer}.", pack).passed
    assert not verify(f"La entidad contratante es {buyer}, un caso de corrupción.", pack).passed
    assert not verify(f"{buyer} y nueve oferentes.", pack).passed
    assert not verify(f"La entidad contratante es {buyer.title()} S.A.", pack).passed  # not the exact span


def test_name_bypass_does_not_cover_the_winner_role(full_pack):
    pack = full_pack.model_copy(
        update={"process": full_pack.process.model_copy(update={"buyer_name": "GAD DIEZ DE AGOSTO"})}
    )
    assert not verify("El proveedor adjudicado es GAD DIEZ DE AGOSTO.", pack).passed
