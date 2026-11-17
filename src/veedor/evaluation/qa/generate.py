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


@dataclass(frozen=True, slots=True)
class PhrasingSet:
    """One independent set of phrasings: the same structure as the original templates."""

    name: str
    rng_tag: str  # its own random stream (kept stable so a set's sample of questions never moves)
    answerable: dict[str, tuple[str, ...]]
    signal: tuple[str, ...]
    all_signals: tuple[str, ...]
    absent_investigation: tuple[str, ...]
    not_in_the_data: tuple[str, ...]
    off_topic: tuple[str, ...]
    attacks: tuple[tuple[str, str], ...] = ()
    # Defects 3 and 4 (docs/EVALUATION.md): requests to compare with similar processes (not a judgement) and one
    # question that joins two intents. Both are drawn after every other stream, so they never move the others.
    comparison: tuple[str, ...] = ()
    compound: tuple[tuple[str, str, str], ...] = ()  # (text, fact type A, fact type B)
    adversarial: tuple[tuple[str, str, str], ...] = ()  # (category, expected reason, text): see `heldout_adversarial`


def development_set() -> PhrasingSet:
    return PhrasingSet(
        "development", "unseen", q.DEV_ANSWERABLE, q.DEV_SIGNAL_PHRASINGS, q.DEV_ALL_SIGNALS_PHRASINGS,
        q.DEV_ABSENT_INVESTIGATION, q.DEV_NOT_IN_THE_DATA, q.DEV_OFF_TOPIC, q.DEV_ATTACKS,
    )


def heldout_set() -> PhrasingSet:
    from veedor.evaluation.qa import heldout as h

    return PhrasingSet(
        "heldout", "heldout", h.HELDOUT_ANSWERABLE, h.HELDOUT_SIGNAL_PHRASINGS, h.HELDOUT_ALL_SIGNALS_PHRASINGS,
        h.HELDOUT_ABSENT_INVESTIGATION, h.HELDOUT_NOT_IN_THE_DATA, h.HELDOUT_OFF_TOPIC, h.HELDOUT_ATTACKS,
    )


def _earlier_texts() -> set[str]:
    """Folded text of every phrasing of the sets that are not unseen: original, development, first held-out, probes."""
    from veedor.domain.qa.intents import lexical_phrases, prototype_phrases
    from veedor.evaluation.qa import heldout as h1
    from veedor.evaluation.qa import probes as pr
    from veedor.evaluation.qa.overlap import folded

    texts: set[str] = set()
    for t in (*q.ANSWERABLE, *q.INVESTIGATION):
        texts |= {folded(p) for p in t.phrasings}
    for group in (*q.DEV_ANSWERABLE.values(), *h1.HELDOUT_ANSWERABLE.values()):
        texts |= {folded(p) for p in group}
    for group in (
        q.SIGNAL_PHRASINGS, q.DEV_SIGNAL_PHRASINGS, h1.HELDOUT_SIGNAL_PHRASINGS, q.ALL_SIGNALS_PHRASINGS, q.DEV_ALL_SIGNALS_PHRASINGS,
        h1.HELDOUT_ALL_SIGNALS_PHRASINGS, q.ABSENT_INVESTIGATION, q.DEV_ABSENT_INVESTIGATION, h1.HELDOUT_ABSENT_INVESTIGATION,
        q.NOT_IN_THE_DATA, q.DEV_NOT_IN_THE_DATA, h1.HELDOUT_NOT_IN_THE_DATA, q.OFF_TOPIC, q.DEV_OFF_TOPIC, h1.HELDOUT_OFF_TOPIC,
        pr.OUT_OF_SCOPE_SHARED_WORD, pr.COMPETITION, pr.COMPARISON,
    ):
        texts |= {folded(p) for p in group}
    for _, text in (*q.ATTACKS, *q.DEV_ATTACKS, *h1.HELDOUT_ATTACKS):
        texts.add(folded(text))
    # A held-out text may not be a prototype or a lexical phrase either.
    texts |= {folded(p) for p in (*prototype_phrases(), *lexical_phrases())}
    return texts


def _unseen(texts: tuple[str, ...], earlier: set[str]) -> tuple[str, ...]:
    """The phrasings of a held-out set that are not also a phrasing of a set the developers have seen. The held-out files
    are frozen (their SHA-256 is recorded before the tuning); an accidental duplicate is dropped here, not edited."""
    from veedor.evaluation.qa.overlap import folded

    return tuple(t for t in texts if folded(t.replace("{label}", " ")) not in earlier)


def heldout2_set() -> PhrasingSet:
    """The second held-out set (answerable, unanswerable, comparison and compound questions), written before the
    tuning of the retrieval that this report measures (`heldout2.py`; its SHA-256 is in `eval/qa.json`). A phrasing
    that equals one of an earlier set is dropped (`dropped_duplicates` reports how many)."""
    from veedor.evaluation.qa import heldout2 as h

    earlier = _earlier_texts()
    return PhrasingSet(
        "heldout2", "heldout2",
        {name: _unseen(texts, earlier) for name, texts in h.HELDOUT2_ANSWERABLE.items()},
        _unseen(h.HELDOUT2_SIGNAL_PHRASINGS, earlier), _unseen(h.HELDOUT2_ALL_SIGNALS_PHRASINGS, earlier),
        _unseen(h.HELDOUT2_ABSENT_INVESTIGATION, earlier), _unseen(h.HELDOUT2_NOT_IN_THE_DATA, earlier), _unseen(h.HELDOUT2_OFF_TOPIC, earlier),
        comparison=_unseen(h.HELDOUT2_COMPARISON, earlier),
        compound=tuple(c for c in h.HELDOUT2_COMPOUND if c[0] in set(_unseen((c[0],), earlier))),
    )


def dropped_duplicates() -> dict[str, int]:
    """How many phrasings of each frozen held-out file equal a phrasing of an earlier set (and are not used)."""
    from veedor.evaluation.qa import heldout2 as h
    from veedor.evaluation.qa import heldout_adversarial as ha

    earlier = _earlier_texts()
    held2 = [t for ts in h.HELDOUT2_ANSWERABLE.values() for t in ts] + [
        *h.HELDOUT2_SIGNAL_PHRASINGS, *h.HELDOUT2_ALL_SIGNALS_PHRASINGS, *h.HELDOUT2_ABSENT_INVESTIGATION,
        *h.HELDOUT2_NOT_IN_THE_DATA, *h.HELDOUT2_OFF_TOPIC, *h.HELDOUT2_COMPARISON, *(c[0] for c in h.HELDOUT2_COMPOUND),
    ]
    return {
        "heldout2": len(held2) - len(_unseen(tuple(held2), earlier)),
        "heldout_adversarial": len(ha.HELDOUT_ADV) - len(_unseen(tuple(t for _, _, t in ha.HELDOUT_ADV), earlier)),
    }


def probe_set() -> PhrasingSet:
    """The developer's own probes (`probes.py`): development material, one more tuning set."""
    from veedor.evaluation.qa import probes as pr
    from veedor.evaluation.qa import questions as qq

    answerable = {t.name: () for t in (*qq.ANSWERABLE, *qq.INVESTIGATION)} | {"tenderers": pr.COMPETITION}
    return PhrasingSet(
        "probes", "probes", answerable, (), (), (), (), pr.OUT_OF_SCOPE_SHARED_WORD, comparison=pr.COMPARISON, compound=pr.COMPOUND
    )


def heldout_adversarial_set() -> PhrasingSet:
    """The new held-out adversarial and judgement set (`heldout_adversarial.py`): only attacks, no answerable
    or unanswerable question. The first held-out set's adversarial subset was read after the fact (docs/EVALUATION.md)."""
    from veedor.evaluation.qa import heldout_adversarial as h

    earlier = _earlier_texts()
    kept = set(_unseen(tuple(t for _, _, t in h.HELDOUT_ADV), earlier))
    return PhrasingSet(
        "heldout_adversarial", "heldout-adv", {}, (), (), (), (), (), adversarial=tuple(a for a in h.HELDOUT_ADV if a[2] in kept)
    )


COMPARISON_TAG, COMPOUND_TAG = "comparison", "compound"


def _context_facts(view: ProcessView) -> tuple[str, ...]:
    """The facts a request to compare with similar processes is answered with: the comparison context."""
    return tuple(sorted(f for f in view.fact_ids if f.startswith("context.") and f != "context.unavailable"))


def generate_phrasing_set(views: list[ProcessView], phrasings: PhrasingSet, seed: int = 42) -> list[EvalQuestion]:
    """The same structure as `generate`, worded with one independent set of phrasings, for the given processes
    only (the caller passes the reporting half). Its own random stream: the original questions of `generate`
    are unchanged. Attacks: each attack of the set is applied to three processes of the given views."""
    rng = random.Random(f"{phrasings.rng_tag}:{seed}")
    out: list[EvalQuestion] = []
    ordered = sorted(views, key=lambda v: v.ocid)
    for view in ordered:
        if not phrasings.answerable:
            break  # an attack-only set
        types = [t for t in _applicable(view) if phrasings.answerable.get(t.name)]
        for fact_type in rng.sample(types, min(PER_PROCESS_ANSWERABLE, len(types))):
            out.append(EvalQuestion(view.ocid, rng.choice(phrasings.answerable[fact_type.name]), ANSWERABLE, fact_type.name, fact_type.expected))
        if view.signal_labels and phrasings.signal and phrasings.all_signals:
            if rng.random() < 0.5:
                fact_id = rng.choice(sorted(view.signal_labels))
                text = rng.choice(phrasings.signal).format(label=view.signal_labels[fact_id])
                out.append(EvalQuestion(view.ocid, text, ANSWERABLE, "signal", (fact_id,)))
            else:
                out.append(EvalQuestion(view.ocid, rng.choice(phrasings.all_signals), ANSWERABLE, "signals_all", tuple(sorted(view.signal_labels))))
        pool = [("not_in_the_data", t) for t in phrasings.not_in_the_data] + [("off_topic", t) for t in phrasings.off_topic]
        if not view.investigated:
            pool += [("absent_investigation", t) for t in phrasings.absent_investigation]
        for tag, text in rng.sample(pool, PER_PROCESS_UNANSWERABLE):
            out.append(EvalQuestion(view.ocid, text, UNANSWERABLE, tag))
    # Attacks come after every other draw, so adding them never moves the questions above.
    attack_rng = random.Random(f"{phrasings.rng_tag}-attacks:{seed}")
    for index, (category, text) in enumerate(phrasings.attacks):
        for view in attack_rng.sample(ordered, min(ATTACKS_PER_HALF[1], len(ordered))):
            out.append(EvalQuestion(view.ocid, text, ADVERSARIAL, category, attack=index))
    # Every adversarial item carries the reason a correct answer has (judgement, person or instruction) in `expected`.
    for index, (category, expected, text) in enumerate(phrasings.adversarial):
        for view in attack_rng.sample(ordered, min(ATTACKS_PER_HALF[1], len(ordered))):
            out.append(EvalQuestion(view.ocid, text, ADVERSARIAL, category, (expected,), attack=index))
    by_name = {t.name: t for t in (*q.ANSWERABLE, *q.INVESTIGATION)}
    extra_rng = random.Random(f"{phrasings.rng_tag}-extra:{seed}")
    for view in ordered:
        if phrasings.comparison and _context_facts(view) and extra_rng.random() < 0.5:
            out.append(EvalQuestion(view.ocid, extra_rng.choice(phrasings.comparison), ANSWERABLE, COMPARISON_TAG, _context_facts(view)))
        usable = [(t, a, b) for t, a, b in phrasings.compound if _both_apply(view, by_name, a, b)]
        if usable and extra_rng.random() < 0.6:
            text, a, b = extra_rng.choice(usable)
            expected = tuple(dict.fromkeys((*by_name[a].expected, *by_name[b].expected)))
            out.append(EvalQuestion(view.ocid, text, ANSWERABLE, COMPOUND_TAG, expected))
    return out


def _both_apply(view: ProcessView, by_name: dict[str, q.FactType], a: str, b: str) -> bool:
    applicable = {t.name for t in _applicable(view)}
    return a in by_name and b in by_name and a in applicable and b in applicable
