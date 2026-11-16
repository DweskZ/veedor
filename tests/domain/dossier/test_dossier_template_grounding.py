"""The template output must pass the verifier 100 % for every fixture, and respect the contract."""

import pytest

from veedor.domain.dossier.assessment import assess
from veedor.domain.dossier.grounding import verify
from veedor.domain.dossier.template import render_template
from veedor.domain.dossier.vocabulary import SECTION_TITLES


def _text(pack):
    n = render_template(pack)
    return n, "\n".join([n.summary_es, *[s.body for s in n.sections]])


@pytest.mark.parametrize("fixture", ["full_pack", "minimal_pack", "natural_pack"])
def test_template_passes_grounding(fixture, request):
    pack = assess(request.getfixturevalue(fixture))
    narrative, text = _text(pack)
    report = verify(text, pack)
    assert report.passed, [t.model_dump() for t in report.unsupported + report.forbidden]
    omitted = ("Contexto registral", "Investigación realizada")  # omitted when empty
    expected = [t for t in SECTION_TITLES if t not in omitted]
    assert [s.title for s in narrative.sections] == expected


def test_missing_facts_render_not_available(minimal_pack):
    _, text = _text(assess(minimal_pack))
    assert "no disponible" in text


def test_limitations_always_state_human_verification(full_pack):
    narrative, _ = _text(full_pack)
    limits = narrative.sections[-1].body
    assert "indicadores de riesgo" in limits and "verificación humana" in limits


def test_natural_person_is_never_named_nor_identified(natural_pack):
    _, text = _text(natural_pack)
    assert "Proveedor adjudicado: persona natural o sin identificar." in text
    assert "0912" not in text and "Persona natural" not in text.split("Proveedor adjudicado")[1][:5]


def test_signals_ordered_with_caveat(full_pack):
    shuffled = full_pack.model_copy(update={"signals": list(reversed(full_pack.signals))})
    assessed = assess(shuffled)
    assert [s.code for s in assessed.signals] == ["SINGLE_BIDDER", "NEW_SUPPLIER"]
    assert all(s.caveat for s in assessed.signals)


def test_spanish_number_format_in_template(full_pack):
    _, text = _text(full_pack)
    assert "USD 27.318,51" in text and "25 de agosto de 2023" in text and "12,3 %" in text
