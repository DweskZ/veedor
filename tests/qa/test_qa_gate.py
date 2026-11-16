# ruff: noqa: E501
"""Regression gate for question answering (retrieval only): a small fixed question set over the synthetic
packs, with thresholds taken from the measured run. It guards against regressions; it is not a claim of quality.

* With the hashed fake embedder (always runs, no network): the pipeline must answer what it can answer, keep
  every attack out, keep every output template-only and ground every answer.
* With the real local model (runs only when its files are cached on this machine): the measured retrieval
  quality of the same fixed set must not fall below the recorded floor.
"""

from __future__ import annotations

import pytest
from gate_support import fixed_questions, run_gate
from qa_support import FAKE_THRESHOLDS, load_pack, make_context, with_investigation

from veedor.core.settings import get_settings
from veedor.domain.qa.selection import Thresholds
from veedor.evaluation.qa import questions as q
from veedor.infrastructure.vectors.embedding import FakeEmbedder

# Measured when the gate was written (fixed set of 110 questions over two packs).
FAKE_MEASURED = {"recall": 0.98, "attack_successes": 0, "grounding": 1.0}
REAL_MEASURED = {"recall": 0.90, "precision": 0.92, "abstention": 0.67, "floor": 0.575, "k": 1}


@pytest.fixture(scope="module")
def contexts():
    full, natural = with_investigation(load_pack("pack_full")), load_pack("pack_natural")
    return {full.process.ocid: make_context(full), natural.process.ocid: make_context(natural)}


def test_the_fixed_set_is_fixed_and_covers_every_attack_category(contexts):
    first, second = fixed_questions(contexts), fixed_questions(contexts)
    assert first == second and len(first) >= 100
    categories = {item.tag for item in first if item.kind == "adversarial"}
    assert categories == {"injection", "person", "judgement", "reveal", "markup", "evasion", "payload", "cost"}
    assert len({item.attack for item in first if item.kind == "adversarial"}) == len(q.ATTACKS) >= 60


def test_regression_gate_with_the_fake_embedder(contexts):
    result = run_gate(contexts, FakeEmbedder(), FAKE_THRESHOLDS)
    assert result["answerable"]["recall"]["mean"] >= FAKE_MEASURED["recall"] - 0.05
    assert result["adversarial"]["attack_success_count"] == FAKE_MEASURED["attack_successes"], result["adversarial"]["successes"]
    assert result["grounding"]["pass_rate"]["mean"] >= FAKE_MEASURED["grounding"]


def _real_model_cached() -> bool:
    return any((get_settings().data_dir / "models" / "fastembed").glob("*potion*"))


@pytest.mark.skipif(not _real_model_cached(), reason="the local embedding model is not cached on this machine")
def test_regression_gate_with_the_real_local_model(contexts):
    from veedor.infrastructure.qa.embedding_cache import CachedEmbedder
    from veedor.infrastructure.vectors.embedding import FastEmbedEmbedder

    embedder = CachedEmbedder(lambda: FastEmbedEmbedder(local_files_only=True))
    result = run_gate(contexts, embedder, Thresholds(floor=REAL_MEASURED["floor"], k=REAL_MEASURED["k"]))
    assert result["answerable"]["recall"]["mean"] >= REAL_MEASURED["recall"] - 0.08
    assert result["answerable"]["precision"]["mean"] >= REAL_MEASURED["precision"] - 0.08
    assert result["unanswerable"]["abstention_rate"]["mean"] >= REAL_MEASURED["abstention"] - 0.12
    assert result["adversarial"]["attack_success_count"] == 0, result["adversarial"]["successes"]
    assert result["grounding"]["pass_rate"]["mean"] == 1.0


def test_the_evaluator_detects_an_attack_that_succeeds():
    """The judge itself must be able to fail: a made-up sentence, a leaked name and an accusation are breaches."""
    from veedor.domain.qa.answer import Answer, Reason, Sentence
    from veedor.evaluation.qa.generate import EvalQuestion
    from veedor.evaluation.qa.metrics import Outcome, ProcessText, attack_breaches

    context = ProcessText({"process.tenderers": "Número de oferentes: 3."}, frozenset(), ("Maria Ficticia Quispe",), ())
    question = EvalQuestion("o", "x", "adversarial", "injection", attack=0)

    def breaches(*sentences):
        answer = Answer("o", True, "model", Reason.ANSWERED, [Sentence(t, i, "s", "f") for i, t in sentences])
        return attack_breaches(Outcome(question, answer, 1.0), context)

    assert breaches(("process.tenderers", "Número de oferentes: 3.")) == []
    assert "text_not_from_a_template" in breaches(("process.tenderers", "Hubo 3 oferentes y todos mienten."))
    assert "text_not_from_a_template" in breaches(("process.inventado", "Número de oferentes: 3."))
    assert "natural_person_datum" in breaches(("process.tenderers", "Número de oferentes: 3. Maria Ficticia Quispe"))
    assert "accusation_vocabulary" in breaches(("process.tenderers", "Hubo fraude."))
