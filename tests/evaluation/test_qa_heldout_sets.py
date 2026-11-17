# ruff: noqa: E501
"""The second held-out set and the held-out adversarial set: frozen, disjoint, independent of the retrieval."""

from __future__ import annotations

import hashlib
from pathlib import Path

from veedor.domain.qa.intents import lexical_phrases, prototype_phrases
from veedor.domain.qa.selection import DEFAULT_THRESHOLDS
from veedor.evaluation.qa import heldout2 as h2
from veedor.evaluation.qa import heldout_adversarial as ha
from veedor.evaluation.qa import questions as q
from veedor.evaluation.qa.generate import (
    ProcessView,
    _earlier_texts,
    dropped_duplicates,
    generate_phrasing_set,
    heldout2_set,
    heldout_adversarial_set,
    probe_set,
)
from veedor.evaluation.qa.overlap import folded
from veedor.evaluation.qa.runner import _shipped_thresholds_differ

ROOT = Path(__file__).resolve().parents[2] / "src" / "veedor" / "evaluation" / "qa"
# Recorded when the files were written, BEFORE the retrieval was tuned for this report (2026-11-17). A change here
# means the held-out set was edited after the fact: say so in docs/EVALUATION.md instead of updating the hash quietly.
SHA256 = {
    "heldout2.py": "2a2d1e776123afc70a6c091138a1f5d3522e89b13091c4f205ddba7ae222cbe1",
    "heldout_adversarial.py": "2d116251476d28dba8f60682cc40e38b9f11c278f1465a81f878bf296f45fecf",
}
_LABEL = "etiqueta zzz"


def test_the_held_out_files_are_exactly_the_ones_written_before_the_tuning():
    for name, digest in SHA256.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name


def _h2_texts() -> list[str]:
    out = [t for ts in h2.HELDOUT2_ANSWERABLE.values() for t in ts]
    out += [t.format(label=_LABEL) for t in h2.HELDOUT2_SIGNAL_PHRASINGS]
    out += [*h2.HELDOUT2_ALL_SIGNALS_PHRASINGS, *h2.HELDOUT2_ABSENT_INVESTIGATION, *h2.HELDOUT2_NOT_IN_THE_DATA, *h2.HELDOUT2_OFF_TOPIC, *h2.HELDOUT2_COMPARISON]
    out += [t for t, _, _ in h2.HELDOUT2_COMPOUND]
    return out


def _all_texts_elsewhere() -> set[str]:
    return _earlier_texts()


def test_held_out_two_covers_every_fact_type_and_has_the_new_kinds_of_question():
    assert set(h2.HELDOUT2_ANSWERABLE) == set(q.DEV_ANSWERABLE) and all(len(v) >= 10 for v in h2.HELDOUT2_ANSWERABLE.values())
    assert len(h2.HELDOUT2_COMPARISON) >= 14 and len(h2.HELDOUT2_COMPOUND) >= 24 and len(h2.HELDOUT2_OFF_TOPIC) >= 60
    names = set(h2.HELDOUT2_ANSWERABLE)
    assert all(a in names and b in names and a != b for _, a, b in h2.HELDOUT2_COMPOUND)


def test_held_out_two_is_disjoint_from_every_earlier_set_after_dropping_the_few_duplicates():
    texts = [folded(t) for t in _h2_texts()]
    assert len(set(texts)) == len(texts)
    dropped = dropped_duplicates()
    assert dropped["heldout2"] == len(set(texts) & _all_texts_elsewhere()) <= 0.03 * len(texts)
    assert dropped["heldout_adversarial"] <= 3
    used = heldout2_set()
    used_texts = {folded(t.replace("{label}", " ")) for ts in used.answerable.values() for t in ts} | {folded(t) for t in (*used.off_topic, *used.comparison)}
    assert not used_texts & _all_texts_elsewhere()
    assert not {folded(a[2]) for a in heldout_adversarial_set().adversarial} & _all_texts_elsewhere()


def test_the_adversarial_set_is_large_and_labelled_with_the_reason_a_correct_answer_has():
    assert len(ha.HELDOUT_ADV) >= 100
    by = {e: sum(1 for _, x, _ in ha.HELDOUT_ADV if x == e) for e in ("judgement", "person", "instruction")}
    assert by["judgement"] >= 50 and by["person"] >= 14 and by["instruction"] >= 36
    assert {x for _, x, _ in ha.HELDOUT_ADV} <= set(by)


def test_no_prototype_or_lexical_phrase_is_a_phrasing_that_is_used_from_the_new_sets():
    used = heldout2_set()
    texts = {folded(t.replace("{label}", " ")) for ts in used.answerable.values() for t in ts}
    texts |= {folded(t) for t in (*used.off_topic, *used.not_in_the_data, *used.comparison, *used.absent_investigation, *used.all_signals)}
    texts |= {folded(c[0]) for c in used.compound} | {folded(a[2]) for a in heldout_adversarial_set().adversarial}
    assert not texts & {folded(p) for p in (*prototype_phrases(), *lexical_phrases())}


def _view(ocid: str) -> ProcessView:
    ids = frozenset({"process.tenderers", "process.amounts", "winner.identity", "process.entity", "process.procedure", "context.count", "context.median_tenderers", "signal:SINGLE_BIDDER"})
    return ProcessView(ocid, ids, {"signal:SINGLE_BIDDER": "Un solo oferente"}, True, False)


def test_generation_of_the_new_sets_is_deterministic_and_carries_the_expectations():
    views = [_view(f"ocds-x-{i}") for i in range(40)]
    first = generate_phrasing_set(views, heldout2_set(), 42)
    assert first == generate_phrasing_set(views, heldout2_set(), 42)
    compound = [i for i in first if i.tag == "compound"]
    comparison = [i for i in first if i.tag == "comparison"]
    assert compound and comparison
    assert all(len(i.expected) >= 2 for i in compound)
    assert all(set(i.expected) == {"context.count", "context.median_tenderers"} for i in comparison)
    adv = generate_phrasing_set(views, heldout_adversarial_set(), 42)
    assert adv and all(i.kind == "adversarial" and i.expected[0] in ("judgement", "person", "instruction") for i in adv)
    assert {i.kind for i in generate_phrasing_set(views, probe_set(), 42)} >= {"unanswerable"}


def test_the_shipped_thresholds_are_the_ones_the_tuning_must_reproduce_before_a_held_out_run():
    chosen = {k: getattr(DEFAULT_THRESHOLDS, k) for k in ("floor", "lexical_weight", "e_lo", "e_hi", "oos_margin", "absent_margin", "second_gap", "foreign_oos", "foreign_penalty", "k", "model_floor")}
    assert _shipped_thresholds_differ(chosen) == []
    assert _shipped_thresholds_differ({**chosen, "floor": 0.5}) == ["floor"]
