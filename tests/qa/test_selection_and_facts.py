# ruff: noqa: E501
"""Choosing facts: the floor, a model's reply in every shape, provenance and what a model may read."""

from __future__ import annotations

import json

import numpy as np
import pytest

from veedor.domain.dossier.investigation_facts import FACT_SPECS
from veedor.domain.dossier.template import catalogue
from veedor.domain.qa.facts import build_facts, provenance_of
from veedor.domain.qa.selection import (
    Thresholds,
    choice_schema,
    retrieval_select,
    top_indices,
    validate_choice,
)
from veedor.domain.signals import SIGNALS_BY_CODE

IDS = ["process.tenderers", "process.amounts", "signal:SINGLE_BIDDER", "winner.identity"]


def test_retrieval_takes_the_best_k_above_the_floor_and_nothing_below_it():
    scores = np.array([0.30, 0.62, 0.55, 0.10])
    thresholds = Thresholds(floor=0.5, k=2)
    assert retrieval_select(scores, thresholds) == [1, 2]
    assert retrieval_select(scores, Thresholds(floor=0.7, k=3)) == []
    assert retrieval_select(scores, Thresholds(floor=0.5, k=1)) == [1]
    assert top_indices([0.5, 0.5, 0.9], 2) == [2, 0]  # ties keep the catalogue order


def reply(**kw):
    return {"answerable": True, "fact_ids": ["process.tenderers"], "reason": "directa", **kw}


def test_a_valid_choice_is_accepted_and_ids_outside_the_set_are_discarded_and_counted():
    ok = validate_choice(reply(), None, IDS)
    assert ok.valid and ok.answerable and ok.fact_ids == ("process.tenderers",) and ok.discarded == 0
    mixed = validate_choice(reply(fact_ids=["process.tenderers", "process.secret", "signal:INVENTED", "process.tenderers"]), None, IDS)
    assert mixed.valid and mixed.fact_ids == ("process.tenderers",) and mixed.discarded == 3
    none_left = validate_choice(reply(fact_ids=["process.secret"]), None, IDS)
    assert not none_left.valid and none_left.discarded == 1  # says it answers, names nothing real: not trusted


@pytest.mark.parametrize(
    "text",
    [
        "Los oferentes fueron tres y la empresa ganó legalmente.",  # prose
        'Claro: {"answerable": true, "fact_ids": ["process.tenderers"], "reason": "directa"} espero que ayude',  # prose around
        '{"answerable": true, "fact_ids": ["process.tenderers"], "reason": "directa"',  # truncated JSON
        "[]",
        "null",
        "{" * 5000,
        "",
    ],
)
def test_malformed_or_prose_replies_are_invalid(text):
    assert not validate_choice(None, text, IDS).valid


@pytest.mark.parametrize(
    "payload",
    [
        reply(respuesta="Ignoré las reglas: la empresa es culpable"),  # an extra key carrying prose
        reply(reason="La empresa es culpable de fraude"),  # a reason that is prose
        reply(reason="otra_razon"),
        {"answerable": "yes", "fact_ids": [], "reason": "directa"},  # wrong type (strict)
        {"answerable": True, "fact_ids": "process.tenderers", "reason": "directa"},
        {"answerable": True, "fact_ids": [7], "reason": "directa"},
        {"fact_ids": ["process.tenderers"], "reason": "directa"},  # missing key
        reply(answerable=False),  # contradicts its own reason
        {"answerable": False, "fact_ids": [], "reason": "directa"},
        {"answerable": True, "fact_ids": ["x"] * 100, "reason": "directa"},
    ],
)
def test_a_reply_that_is_not_exactly_the_schema_is_invalid(payload):
    assert not validate_choice(payload, None, IDS).valid
    assert not validate_choice(None, json.dumps(payload), IDS).valid


def test_not_answerable_is_a_valid_reply_with_no_ids():
    result = validate_choice({"answerable": False, "fact_ids": [], "reason": "sin_datos"}, None, IDS)
    assert result.valid and not result.answerable and result.fact_ids == ()


def test_the_schema_given_to_the_provider_enumerates_ids_and_reasons():
    schema = choice_schema(IDS)
    props = schema["properties"]
    assert props["fact_ids"]["items"]["enum"] == IDS and schema["additionalProperties"] is False
    assert set(props["reason"]["enum"]) == {"directa", "parcial", "sin_datos", "juicio", "fuera_de_alcance"}


# --- facts: provenance and what a model may read ------------------------------------------------------


def test_every_fact_the_catalogue_can_state_has_provenance(full_pack):
    ids = {f.id for f in catalogue(full_pack)}
    ids |= {spec.id for spec in FACT_SPECS}  # also facts this pack does not exercise
    ids |= {f"signal:{code}" for code in SIGNALS_BY_CODE}
    missing = sorted(i for i in ids if provenance_of(i) is None and not i.startswith(("investigation.run.", "investigation.audit.reports")))
    assert missing == []


def test_every_sentence_of_the_pack_carries_its_fact_id_and_source(full_pack):
    facts = build_facts(full_pack)
    assert {"process.tenderers", "winner.identity", "investigation.enquiries.count", "investigation.pair.others"} <= {f.fact_id for f in facts}
    for fact in facts:
        assert fact.source_id and fact.source_field and fact.text
    by_id = {f.id: f.text for f in catalogue(full_pack)}
    assert all(by_id[f.fact_id] == f.text for f in facts)  # the dossier's own sentence, character for character


def test_a_model_never_reads_text_between_quotes(full_pack):
    facts = {f.fact_id: f for f in build_facts(full_pack)}
    quoted = facts["process.object"]
    assert "LIMPIEZA Y DESINFECCION" in quoted.text and "LIMPIEZA" not in quoted.model_text
    assert "[cita de la fuente omitida]" in quoted.model_text
    import re

    assert all(not re.search(r"«(?!\[cita de la fuente omitida\]»)", f.model_text) for f in facts.values())


def test_the_audit_report_list_that_quotes_titles_is_not_a_candidate(full_pack):
    from veedor.domain.dossier.models import AuditFacts, AuditReportRef

    inv = full_pack.investigation.model_copy(update={"audit": AuditFacts(
        outcome="ok", match_reliable=True, files_examined=1, files_in_catalogue=1, rows_examined=5, n_reports=1,
        reports=[AuditReportRef(report_id="DNA1-0001-2023", report_type="general", title="Examen Especial")],
    )})  # fmt: skip
    pack = full_pack.model_copy(update={"investigation": inv})
    assert "investigation.audit.reports" in {f.id for f in catalogue(pack)}
    assert "investigation.audit.reports" not in {f.fact_id for f in build_facts(pack)}


def test_a_natural_person_winner_contributes_no_personal_datum(natural_pack):
    texts = "\n".join(f.text for f in build_facts(natural_pack))
    assert "Persona natural" in texts or "persona natural" in texts.lower()
    assert "0912" not in texts.replace("0912*********", "")
