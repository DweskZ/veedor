# ruff: noqa: E501
"""The evaluation sets are generated from the data, seeded and deterministic; the split never straddles a process."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qa"))

from qa_support import load_pack, make_context, with_investigation  # noqa: E402

from veedor.evaluation.qa import questions as q  # noqa: E402
from veedor.evaluation.qa.generate import ADVERSARIAL, ANSWERABLE, UNANSWERABLE, ProcessView, generate  # noqa: E402
from veedor.evaluation.qa.runner import split_of, views_of  # noqa: E402


def views(n: int = 40, investigated: bool = False) -> list[ProcessView]:
    full = with_investigation(load_pack("pack_full"))
    ctx = make_context(full)
    out = []
    for i in range(n):
        out += views_of({f"ocds-5wno2w-V-{i:03d}": ctx}, {f"ocds-5wno2w-V-{i:03d}"} if investigated else set())
    return out


def test_same_seed_same_questions_in_the_same_order():
    assert generate(views(), 42) == generate(views(), 42)
    assert generate(views(), 42) != generate(views(), 43)


def test_expected_fact_ids_are_known_by_construction_and_exist_in_the_process():
    by_ocid = {v.ocid: v for v in views()}
    items = [i for i in generate(views(), 42) if i.kind == ANSWERABLE]
    assert items
    for item in items:
        assert set(item.expected) <= by_ocid[item.ocid].fact_ids


def test_every_fact_type_has_several_phrasings_including_informal_ones():
    assert all(len(t.phrasings) >= 2 for t in q.ANSWERABLE)
    informal = [p for t in q.ANSWERABLE for p in t.phrasings if not p.startswith("¿") and p == p.lower()]
    assert len(informal) >= 15
    assert any(p != p.lower() for t in q.ANSWERABLE for p in t.phrasings)


def test_unanswerable_questions_about_an_investigation_appear_only_for_processes_without_one():
    plain = {i.text for i in generate(views(60), 1) if i.tag == "absent_investigation"}
    assert plain and plain <= set(q.ABSENT_INVESTIGATION)
    assert not [i for i in generate(views(60, investigated=True), 1) if i.tag == "absent_investigation"]


def test_there_are_at_least_sixty_distinct_attacks_in_the_listed_categories_applied_to_both_halves():
    assert len({text for _, text in q.ATTACKS}) >= 60
    assert {c for c, _ in q.ATTACKS} >= {"injection", "person", "judgement", "reveal", "markup", "evasion", "payload", "cost"}
    items = [i for i in generate(views(120), 42, split_of) if i.kind == ADVERSARIAL]
    for half in ("tune", "report"):
        assert len({i.attack for i in items if split_of(i.ocid) == half}) == len(q.ATTACKS)


def test_the_split_is_stable_and_roughly_even():
    ocids = [f"ocds-5wno2w-V-{i:04d}" for i in range(2000)]
    halves = [split_of(o) for o in ocids]
    assert halves == [split_of(o) for o in ocids]
    assert 0.45 < halves.count("tune") / len(halves) < 0.55


def test_all_three_sets_are_produced():
    kinds = {i.kind for i in generate(views(), 42)}
    assert kinds == {ANSWERABLE, UNANSWERABLE, ADVERSARIAL}
