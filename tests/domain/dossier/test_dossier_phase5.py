"""Every phrase the model can choose renders and verifies; applicability predicates; versioning."""

import pytest

from veedor.domain.dossier.assessment import assess
from veedor.domain.dossier.grounding import verify
from veedor.domain.dossier.models import Dossier, SignalFact, WinnerFacts
from veedor.domain.dossier.plan import (
    CONNECTIVES,
    REVIEWER_NOTES,
    PlanError,
    RenderPlan,
    applicable_notes,
)
from veedor.domain.dossier.template import catalogue, render_plan, validate_plan
from veedor.domain.dossier.version import RENDERER_VERSION
from veedor.domain.dossier.vocabulary import SECTION_LIMITS

CONTEXT_SIGNAL = SignalFact(
    code="GHOST_COMPANY_LISTED_LATER", label_es="Proveedor en el listado, con fecha posterior",
    value=1.0, threshold=1.0, evidence={"notification_date": "2025-01-10", "process_date": "2023-08-25"},
)  # fmt: skip


def _text(narrative):
    return narrative.summary_es + "\n" + "\n".join(f"{s.title}\n{s.body}" for s in narrative.sections)


@pytest.fixture
def packs(full_pack, minimal_pack, natural_pack):
    no_signals = full_pack.model_copy(update={"signals": []})
    with_context = full_pack.model_copy(update={"signals": [*full_pack.signals, CONTEXT_SIGNAL]})
    return {
        "full": assess(full_pack),
        "minimal": assess(minimal_pack),
        "natural": assess(natural_pack),
        "no_signals": assess(no_signals),
        "with_context": assess(with_context),
    }


def test_every_connective_in_every_section_renders_and_verifies(packs):
    checked = 0
    for name, pack in packs.items():
        sections = list(dict.fromkeys(f.section for f in catalogue(pack)))
        for ident, phrase in CONNECTIVES.items():  # the same dict the model is offered
            for section in sections:
                plan = RenderPlan(sections={section: [ident]})
                if not phrase.applies(pack, section):
                    with pytest.raises(PlanError):
                        validate_plan(plan, pack)
                    continue
                report = verify(_text(render_plan(pack, plan)), pack)
                assert report.passed, (name, ident, section, [t.model_dump() for t in report.unsupported])
                checked += 1
    assert checked >= 20


def test_every_reviewer_note_renders_and_verifies_where_it_applies(packs):
    checked = 0
    for name, pack in packs.items():
        for ident, phrase in REVIEWER_NOTES.items():
            plan = RenderPlan(reviewer_note=ident)
            if not phrase.applies(pack, None):
                with pytest.raises(PlanError):
                    validate_plan(plan, pack)
                continue
            text = _text(render_plan(pack, plan))
            assert phrase.text in text
            report = verify(text, pack)
            assert report.passed, (name, ident, [t.model_dump() for t in report.unsupported])
            checked += 1
    assert checked >= 8


def test_note_about_signals_needs_risk_signals(packs):
    assert "senales" in applicable_notes(packs["full"])
    assert "senales" not in applicable_notes(packs["no_signals"])
    assert "senales" not in applicable_notes(packs["minimal"])
    # a registry-context signal is not a risk signal
    only_context = packs["with_context"].model_copy(update={"signals": [CONTEXT_SIGNAL]})
    assert "senales" not in applicable_notes(only_context)
    with pytest.raises(PlanError):
        validate_plan(RenderPlan(reviewer_note="senales"), packs["no_signals"])


def test_note_about_the_supplier_needs_an_identified_company(packs, full_pack):
    assert "proveedor" in applicable_notes(packs["full"])
    assert "proveedor" not in applicable_notes(packs["natural"])
    assert "proveedor" not in applicable_notes(packs["minimal"])
    unknown = full_pack.model_copy(update={"winner": WinnerFacts(ruc=None, name=None, kind="unknown")})
    assert "proveedor" not in applicable_notes(unknown)


def test_note_about_context_needs_comparison_and_neutral_note_always_applies(packs):
    assert "contexto" in applicable_notes(packs["full"]) and "contexto" not in applicable_notes(
        packs["minimal"]
    )
    assert all("sin_prioridad" in applicable_notes(p) for p in packs.values())


def test_context_connective_only_in_context_sections(packs):
    pack = packs["full"]
    assert CONNECTIVES["conn:contexto"].applies(pack, "Contexto comparativo")
    assert not CONNECTIVES["conn:contexto"].applies(pack, "Qué se contrató")
    with pytest.raises(PlanError):
        validate_plan(RenderPlan(sections={"Qué se contrató": ["conn:contexto"]}), pack)


def test_the_limitations_section_cannot_be_planned(packs):
    with pytest.raises(PlanError):
        validate_plan(RenderPlan(sections={SECTION_LIMITS: ["conn:detalle"]}), packs["full"])


def test_dossier_model_carries_the_renderer_version():
    assert RENDERER_VERSION >= 5
    assert Dossier.model_fields["renderer_version"].default == 0  # unversioned entries never match
