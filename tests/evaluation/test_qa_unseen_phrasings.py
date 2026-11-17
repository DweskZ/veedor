"""The unseen question set is independent of the retrieval key phrases (Finding 3 of review 5)."""

from __future__ import annotations

import re

import pytest

from veedor.domain.qa.facts import FACT_KEYS_ES
from veedor.evaluation.qa import questions as q
from veedor.evaluation.qa.generate import ProcessView, generate, generate_unseen
from veedor.evaluation.qa.overlap import equals_or_contains, folded, key_phrases, nearest_overlap

# The signal labels are the deliberate anchor of a signal question; the template is what must differ.
_LABEL = "etiqueta zzz"


def _all_unseen() -> list[tuple[str, str]]:
    out = [(name, text) for name, texts in q.UNSEEN_ANSWERABLE.items() for text in texts]
    out += [("signal", t.format(label=_LABEL)) for t in q.UNSEEN_SIGNAL_PHRASINGS]
    out += [("signals_all", t) for t in q.UNSEEN_ALL_SIGNALS_PHRASINGS]
    out += [("absent_investigation", t) for t in q.UNSEEN_ABSENT_INVESTIGATION]
    out += [("not_in_the_data", t) for t in q.UNSEEN_NOT_IN_THE_DATA]
    out += [("off_topic", t) for t in q.UNSEEN_OFF_TOPIC]
    return out


def test_every_fact_type_has_at_least_five_unseen_phrasings():
    types = {t.name for t in (*q.ANSWERABLE, *q.INVESTIGATION)}
    assert types == set(q.UNSEEN_ANSWERABLE)
    assert all(len(v) >= 5 for v in q.UNSEEN_ANSWERABLE.values())
    assert len(q.UNSEEN_SIGNAL_PHRASINGS) >= 5 and len(q.UNSEEN_ALL_SIGNALS_PHRASINGS) >= 5
    assert (
        min(len(q.UNSEEN_NOT_IN_THE_DATA), len(q.UNSEEN_OFF_TOPIC), len(q.UNSEEN_ABSENT_INVESTIGATION)) >= 5
    )


@pytest.mark.parametrize(("name", "text"), _all_unseen())
def test_no_unseen_phrasing_equals_or_contains_a_retrieval_key(name: str, text: str):
    assert equals_or_contains(text) is None, (name, text)


@pytest.mark.parametrize(("name", "text"), _all_unseen())
def test_token_overlap_with_the_nearest_key_is_below_the_threshold(name: str, text: str):
    score, phrase = nearest_overlap(text.replace(_LABEL, " "))
    assert score < q.MAX_KEY_OVERLAP, (name, text, score, phrase)


def test_unseen_phrasings_are_not_in_the_retrieval_keys_and_not_in_the_old_set():
    keys = folded(" ; ".join(FACT_KEYS_ES.values()))
    old = {folded(p) for t in (*q.ANSWERABLE, *q.INVESTIGATION) for p in t.phrasings}
    for _name, text in _all_unseen():
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


def test_unseen_questions_use_only_unseen_wording_and_leave_the_original_set_unchanged():
    views = [_view(f"ocds-x-{i}") for i in range(30)]
    before = generate(views, 42)
    unseen = generate_unseen(views, 42)
    assert generate(views, 42) == before  # the original stream is untouched
    assert unseen and all(item.attack is None for item in unseen)
    old_texts = {p for t in (*q.ANSWERABLE, *q.INVESTIGATION) for p in t.phrasings}
    answerable = [
        item for item in unseen if item.kind == "answerable" and item.tag not in ("signal", "signals_all")
    ]
    assert answerable and all(item.text not in old_texts for item in answerable)
    assert all(re.search(r"[a-z]", item.text) for item in unseen)
