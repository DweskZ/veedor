# ruff: noqa: E501
"""Generate the three question sets from the data (answerable, unanswerable, adversarial), seeded."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from veedor.domain.qa.facts import QaFact
from veedor.evaluation.qa import questions as q

ANSWERABLE, UNANSWERABLE, ADVERSARIAL = "answerable", "unanswerable", "adversarial"
PER_PROCESS_ANSWERABLE = 4
PER_PROCESS_UNANSWERABLE = 3
ATTACKS_PER_HALF = (2, 3)  # processes per attack: (tuning half, reporting half)


@dataclass(frozen=True, slots=True)
class EvalQuestion:
    ocid: str
    text: str
    kind: str  # answerable | unanswerable | adversarial
    tag: str  # fact type, unanswerable group or attack category
    expected: tuple[str, ...] = ()  # fact ids a correct answer selects (answerable only)
    attack: int | None = None  # index into ATTACKS


@dataclass(frozen=True, slots=True)
class ProcessView:
    """What the generator needs to know about a process: its fact ids, signals and winner kind."""

    ocid: str
    fact_ids: frozenset[str]
    signal_labels: dict[str, str]  # signal fact id -> Spanish label
    company_winner: bool
    investigated: bool


def view_of(ocid: str, facts: list[QaFact], signal_labels: dict[str, str], company_winner: bool, investigated: bool) -> ProcessView:
    return ProcessView(ocid, frozenset(f.fact_id for f in facts), signal_labels, company_winner, investigated)


def _applicable(view: ProcessView) -> list[q.FactType]:
    types = [*q.ANSWERABLE, *(q.INVESTIGATION if view.investigated else ())]
    return [
        t for t in types if set(t.expected) <= view.fact_ids and (view.company_winner or not t.needs_company_winner)
    ]


def _signal_question(view: ProcessView, rng: random.Random) -> EvalQuestion | None:
    if not view.signal_labels:
        return None
    if rng.random() < 0.5:
        fact_id = rng.choice(sorted(view.signal_labels))
        text = rng.choice(q.SIGNAL_PHRASINGS).format(label=view.signal_labels[fact_id])
        return EvalQuestion(view.ocid, text, ANSWERABLE, "signal", (fact_id,))
    return EvalQuestion(view.ocid, rng.choice(q.ALL_SIGNALS_PHRASINGS), ANSWERABLE, "signals_all", tuple(sorted(view.signal_labels)))


def generate(
    views: list[ProcessView], seed: int = 42, half_of: Callable[[str], str] = lambda ocid: "report"
) -> list[EvalQuestion]:
    """Questions for the given processes. Same views and seed: same questions, in the same order.

    `half_of` says which half (``tune`` or ``report``) a process belongs to: every attack is applied to
    processes of both halves, so every attack is also reported on."""
    rng = random.Random(seed)
    out: list[EvalQuestion] = []
    ordered = sorted(views, key=lambda v: v.ocid)
    for view in ordered:
        types = _applicable(view)
        for fact_type in rng.sample(types, min(PER_PROCESS_ANSWERABLE, len(types))):
            out.append(EvalQuestion(view.ocid, rng.choice(fact_type.phrasings), ANSWERABLE, fact_type.name, fact_type.expected))
        if (signal := _signal_question(view, rng)) is not None:
            out.append(signal)
        pool = [("not_in_the_data", t) for t in q.NOT_IN_THE_DATA] + [("off_topic", t) for t in q.OFF_TOPIC]
        if not view.investigated:
            pool += [("absent_investigation", t) for t in q.ABSENT_INVESTIGATION]
        for tag, text in rng.sample(pool, PER_PROCESS_UNANSWERABLE):
            out.append(EvalQuestion(view.ocid, text, UNANSWERABLE, tag))
    halves = {name: [v for v in ordered if half_of(v.ocid) == name] for name in ("tune", "report")}
    for index, (category, text) in enumerate(q.ATTACKS):
        for name, count in zip(("tune", "report"), ATTACKS_PER_HALF, strict=True):
            for view in rng.sample(halves[name], min(count, len(halves[name]))):
                out.append(EvalQuestion(view.ocid, text, ADVERSARIAL, category, attack=index))
    return out


def generate_unseen(views: list[ProcessView], seed: int = 42) -> list[EvalQuestion]:
    """The same structure as `generate`, worded with the unseen phrasings (`questions.UNSEEN_*`), for the
    given processes only (the caller passes the reporting half). Its own random stream: the in-vocabulary
    questions of `generate` are unchanged. No attacks: those are not about retrieval keys."""
    rng = random.Random(f"unseen:{seed}")
    out: list[EvalQuestion] = []
    for view in sorted(views, key=lambda v: v.ocid):
        types = _applicable(view)
        for fact_type in rng.sample(types, min(PER_PROCESS_ANSWERABLE, len(types))):
            out.append(EvalQuestion(view.ocid, rng.choice(q.UNSEEN_ANSWERABLE[fact_type.name]), ANSWERABLE, fact_type.name, fact_type.expected))
        if view.signal_labels:
            if rng.random() < 0.5:
                fact_id = rng.choice(sorted(view.signal_labels))
                text = rng.choice(q.UNSEEN_SIGNAL_PHRASINGS).format(label=view.signal_labels[fact_id])
                out.append(EvalQuestion(view.ocid, text, ANSWERABLE, "signal", (fact_id,)))
            else:
                out.append(EvalQuestion(view.ocid, rng.choice(q.UNSEEN_ALL_SIGNALS_PHRASINGS), ANSWERABLE, "signals_all", tuple(sorted(view.signal_labels))))
        pool = [("not_in_the_data", t) for t in q.UNSEEN_NOT_IN_THE_DATA] + [("off_topic", t) for t in q.UNSEEN_OFF_TOPIC]
        if not view.investigated:
            pool += [("absent_investigation", t) for t in q.UNSEEN_ABSENT_INVESTIGATION]
        for tag, text in rng.sample(pool, PER_PROCESS_UNANSWERABLE):
            out.append(EvalQuestion(view.ocid, text, UNANSWERABLE, tag))
    return out
