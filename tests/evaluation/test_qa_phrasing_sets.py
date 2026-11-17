# ruff: noqa: E501
"""The three phrasing sets (original, development, held-out) are disjoint and independent of the retrieval keys
(finding 3 of review 5)."""

from __future__ import annotations

import re

import pytest

from veedor.domain.qa.facts import FACT_KEYS_ES
from veedor.evaluation.qa import heldout as h
from veedor.evaluation.qa import questions as q
from veedor.evaluation.qa.generate import (
    ProcessView,
    development_set,
    generate,
    generate_phrasing_set,
    heldout_set,
)
from veedor.evaluation.qa.overlap import (
    content_stems,
    equals_or_contains,
    folded,
    key_phrases,
    nearest_overlap,
)

# The signal labels are the deliberate anchor of a signal question; the template is what must differ.
_LABEL = "etiqueta zzz"


def _all_dev() -> list[tuple[str, str]]:
    out = [(name, text) for name, texts in q.DEV_ANSWERABLE.items() for text in texts]
    out += [("signal", t.format(label=_LABEL)) for t in q.DEV_SIGNAL_PHRASINGS]
    out += [("signals_all", t) for t in q.DEV_ALL_SIGNALS_PHRASINGS]
    out += [("absent_investigation", t) for t in q.DEV_ABSENT_INVESTIGATION]
    out += [("not_in_the_data", t) for t in q.DEV_NOT_IN_THE_DATA]
    out += [("off_topic", t) for t in q.DEV_OFF_TOPIC]
    return out


def test_every_fact_type_has_at_least_five_development_phrasings():
    types = {t.name for t in (*q.ANSWERABLE, *q.INVESTIGATION)}
    assert types == set(q.DEV_ANSWERABLE)
    assert all(len(v) >= 5 for v in q.DEV_ANSWERABLE.values())
    assert len(q.DEV_SIGNAL_PHRASINGS) >= 5 and len(q.DEV_ALL_SIGNALS_PHRASINGS) >= 5
    assert (
        min(len(q.DEV_NOT_IN_THE_DATA), len(q.DEV_OFF_TOPIC), len(q.DEV_ABSENT_INVESTIGATION)) >= 5
    )


@pytest.mark.parametrize(("name", "text"), _all_dev())
def test_no_development_phrasing_equals_or_contains_a_retrieval_key(name: str, text: str):
    assert equals_or_contains(text) is None, (name, text)


@pytest.mark.parametrize(("name", "text"), _all_dev())
def test_token_overlap_with_the_nearest_key_is_below_the_threshold(name: str, text: str):
    score, phrase = nearest_overlap(text.replace(_LABEL, " "))
    assert score < q.MAX_KEY_OVERLAP, (name, text, score, phrase)


def test_development_phrasings_are_not_in_the_retrieval_keys_and_not_in_the_old_set():
    keys = folded(" ; ".join(FACT_KEYS_ES.values()))
    old = {folded(p) for t in (*q.ANSWERABLE, *q.INVESTIGATION) for p in t.phrasings}
    for _name, text in _all_dev():
        assert folded(text) not in keys
        assert folded(text) not in old


def test_the_old_phrasings_do_leak_which_is_why_the_unseen_set_exists():
    """Documents the reviewer's finding with the same measure: many original templates are keys."""
    phrases = {folded(p) for p in key_phrases()}
    old = [p for t in (*q.ANSWERABLE, *q.INVESTIGATION) for p in t.phrasings]
    verbatim = [p for p in old if folded(p) in phrases]
    assert len(verbatim) >= 20


def _view(ocid: str) -> ProcessView:
    ids = frozenset(
        {"process.tenderers", "process.amounts", "winner.identity", "process.entity", "process.procedure",
         "signal:SINGLE_BIDDER"}
    )  # fmt: skip
    return ProcessView(ocid, ids, {"signal:SINGLE_BIDDER": "Un solo oferente"}, True, False)


def test_development_questions_use_only_development_wording_and_leave_the_original_set_unchanged():
    views = [_view(f"ocds-x-{i}") for i in range(30)]
    before = generate(views, 42)
    dev = generate_phrasing_set(views, development_set(), 42)
    assert generate(views, 42) == before  # the original stream is untouched
    assert dev and all(item.attack is not None for item in dev if item.kind == "adversarial")
    old_texts = {p for t in (*q.ANSWERABLE, *q.INVESTIGATION) for p in t.phrasings}
    answerable = [
        item for item in dev if item.kind == "answerable" and item.tag not in ("signal", "signals_all")
    ]
    assert answerable and all(item.text not in old_texts for item in answerable)
    assert all(re.search(r"[a-z]", item.text) for item in dev)


# --- the held-out test set ---------------------------------------------------------------------------------


def _all_heldout() -> list[tuple[str, str]]:
    out = [(name, text) for name, texts in h.HELDOUT_ANSWERABLE.items() for text in texts]
    out += [("signal", t.format(label=_LABEL)) for t in h.HELDOUT_SIGNAL_PHRASINGS]
    out += [("signals_all", t) for t in h.HELDOUT_ALL_SIGNALS_PHRASINGS]
    out += [("absent_investigation", t) for t in h.HELDOUT_ABSENT_INVESTIGATION]
    out += [("not_in_the_data", t) for t in h.HELDOUT_NOT_IN_THE_DATA]
    out += [("off_topic", t) for t in h.HELDOUT_OFF_TOPIC]
    return out


def _original_texts() -> set[str]:
    out = {folded(p) for t in (*q.ANSWERABLE, *q.INVESTIGATION) for p in t.phrasings}
    out |= {folded(t.format(label=_LABEL)) for t in (*q.SIGNAL_PHRASINGS, *q.DEV_SIGNAL_PHRASINGS)}
    out |= {folded(t) for t in (*q.ALL_SIGNALS_PHRASINGS, *q.ABSENT_INVESTIGATION, *q.NOT_IN_THE_DATA, *q.OFF_TOPIC)}
    return out


def _development_texts() -> set[str]:
    return {folded(text) for _, text in _all_dev()} | {folded(t) for _, t in q.DEV_ATTACKS}


def test_the_held_out_set_covers_every_fact_type_and_group_and_is_not_tiny():
    assert set(h.HELDOUT_ANSWERABLE) == set(q.DEV_ANSWERABLE)
    assert all(len(v) >= 8 for v in h.HELDOUT_ANSWERABLE.values())
    assert len(h.HELDOUT_SIGNAL_PHRASINGS) >= 8 and len(h.HELDOUT_ALL_SIGNALS_PHRASINGS) >= 8
    assert min(len(h.HELDOUT_NOT_IN_THE_DATA), len(h.HELDOUT_OFF_TOPIC), len(h.HELDOUT_ABSENT_INVESTIGATION)) >= 8
    assert len({t for _, t in h.HELDOUT_ATTACKS}) >= 40
    assert {c for c, _ in h.HELDOUT_ATTACKS} >= {"judgement", "injection", "person", "markup", "payload", "evasion"}


def test_the_held_out_set_is_disjoint_from_the_original_and_the_development_sets():
    heldout = [folded(text) for _, text in _all_heldout()] + [folded(t) for _, t in h.HELDOUT_ATTACKS]
    assert len(set(heldout)) == len(heldout)  # no duplicates inside the set either
    original, development = _original_texts(), _development_texts()
    original_attacks = {folded(t) for _, t in q.ATTACKS}
    for text in heldout:
        assert text not in original, text
        assert text not in development, text
        assert text not in original_attacks, text


def _single_word(text: str) -> bool:
    return len(folded(text).split()) == 1


@pytest.mark.parametrize(("name", "text"), _all_heldout())
def test_no_held_out_phrasing_equals_or_contains_a_retrieval_key(name: str, text: str):
    """A one-word keyword ("ganador?") is necessarily a substring of some key phrase: for those the rule is
    that it is not a key itself (their number is bounded by the next test)."""
    if _single_word(text):
        assert folded(text) not in {folded(p) for p in key_phrases()}, (name, text)
        return
    assert equals_or_contains(text.replace(_LABEL, " ")) is None, (name, text)


@pytest.mark.parametrize(("name", "text"), _all_heldout())
def test_token_overlap_of_a_held_out_phrasing_with_the_nearest_key_is_below_the_threshold(name: str, text: str):
    """Only for questions with at least four content words: the Jaccard index of a two-word keyword query
    against a short key phrase is dominated by one shared concept word, which a natural short query cannot
    avoid ("capital de la empresa"). Those are bounded by the containment rule above."""
    if len(content_stems(text.replace(_LABEL, " "))) < 4:
        return
    score, phrase = nearest_overlap(text.replace(_LABEL, " "))
    assert score < q.MAX_KEY_OVERLAP, (name, text, score, phrase)


def test_one_word_keyword_queries_are_a_small_minority_of_the_held_out_set():
    singles = [t for _, t in _all_heldout() if _single_word(t)]
    assert 1 <= len(singles) <= 0.06 * len(_all_heldout())


def test_no_retrieval_prototype_or_lexical_phrase_is_a_held_out_phrasing():
    """The retrieval was tuned without the held-out set. A prototype question may not equal or contain a
    held-out phrasing (nor sit inside one of four words or more); a lexical concept phrase ("en que consiste") may not be a whole one."""
    from veedor.domain.qa.intents import lexical_phrases, prototype_phrases

    heldout = [f" {folded(text.replace(_LABEL, ' '))} " for _, text in _all_heldout()]
    for phrase in prototype_phrases():
        p = f" {folded(phrase)} "
        for text in heldout:
            assert p != text, (phrase, text)
            if len(p.split()) >= 3:
                assert p not in text, (phrase, text)
            if len(text.split()) >= 4:  # a three-word keyword query may sit inside a long prototype
                assert text not in p, (phrase, text)
    for phrase in lexical_phrases():
        assert all(f" {folded(phrase)} " != text for text in heldout), phrase


def test_held_out_generation_is_deterministic_and_leaves_the_other_streams_untouched():
    views = [_view(f"ocds-x-{i}") for i in range(30)]
    first = generate_phrasing_set(views, heldout_set(), 42)
    assert first == generate_phrasing_set(views, heldout_set(), 42)
    assert generate(views, 42) == generate(views, 42)
    dev = generate_phrasing_set(views, development_set(), 42)
    assert {i.text for i in first if i.kind != "adversarial"}.isdisjoint({i.text for i in dev if i.kind != "adversarial"})
    assert {i.attack for i in first if i.kind == "adversarial"} == set(range(len(h.HELDOUT_ATTACKS)))
