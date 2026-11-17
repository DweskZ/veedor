# ruff: noqa: E501
"""Scoring a question against intents and choosing facts without a model (pure, numpy only).

    question --embedding--> nearest prototype of every intent  \
    question --lexicon----> weighted terms of every intent      >  fused score per intent  -> decision
    signal facts of the process --own keys--> one score each   /

The decision is made over *all* intents, including the ones whose facts this process does not have and the
`oos` intent (what the evidence never answers): the question is answered only when the winning intent has
facts here and beats `oos` by a margin. A question about the number of employees, for a process without a
stored investigation, therefore gets "the evidence does not answer" instead of a neighbouring fact.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from veedor.domain.qa.intents import (
    FACT_INTENT,
    INTENTS,
    OOS_ID,
    SIGNAL_PREFIX,
    SIGNALS_ID,
    embedding_variants,
    fold_text,
    key_phrases_of,
    lexical_scores,
)
from veedor.domain.qa.selection import Thresholds

MAX_GROUP_FACTS = 8  # a signals question is answered with every signal fact, up to this many


class IntentIndex:
    """The prototype embeddings of every static intent, built once from an embedder."""

    def __init__(self, embed: Callable[[Sequence[str]], np.ndarray]) -> None:
        self.ids: tuple[str, ...] = tuple(spec.id for spec in INTENTS)
        phrases: list[str] = []
        owner: list[int] = []
        for position, spec in enumerate(INTENTS):
            for phrase in dict.fromkeys(p for raw in key_phrases_of(spec) for p in embedding_variants(raw)):
                phrases.append(phrase)
                owner.append(position)
        self.owner = np.asarray(owner, dtype=int)
        self.matrix = embed(phrases) if phrases else np.zeros((0, 0), dtype=np.float32)


@dataclass(frozen=True, slots=True)
class IntentScores:
    """Per intent: best cosine to a prototype and lexical score. Static intents first, then one entry per
    signal fact of the process (`signal:CODE`, embedding only)."""

    ids: tuple[str, ...]
    embedding: np.ndarray
    lexical: np.ndarray


_STEM = 5
_LABEL_STOP = frozenset("de del la las el los en un una al a y o que con por para ya se su sus".split())
# Words every question about a process uses: they do not tell one signal from another, so they do not count
# when matching a question against a signal's label ("adjudicaciones ... proveedor" names no signal).
_GENERIC = frozenset(
    "prove adjud ofere entid empre proce contr compa listad sri ante al mome dado fecha".split()
)


def _stems(text: str, *, distinctive: bool = False) -> frozenset[str]:
    stems = frozenset(w[:_STEM] for w in fold_text(text).split() if w not in _LABEL_STOP and len(w) > 2)
    return stems - _GENERIC if distinctive else stems


def raw_scores(
    index: IntentIndex, query: np.ndarray, text: str, signals: Mapping[str, tuple[np.ndarray, str]]
) -> IntentScores:
    """`query`: unit vectors of the question variants; `signals`: per signal fact id, unit vectors of its keys and
    sentence, and its label. A signal is also scored lexically by the share of its label's words the question uses."""
    n = len(index.ids)
    best = np.full(n, -1.0, dtype=np.float32)
    if index.matrix.shape[0]:
        sims = (index.matrix @ query.T).max(axis=1)
        np.maximum.at(best, index.owner, sims)
    lex = lexical_scores(text)
    lexical = [lex[i] for i in index.ids]
    ids = list(index.ids)
    extra: list[float] = []
    mine = _stems(text)
    for fact_id, (vectors, label) in signals.items():
        ids.append(fact_id)
        extra.append(float((vectors @ query.T).max()) if vectors.shape[0] else -1.0)
        words = _stems(label, distinctive=True)
        lexical.append(len(words & mine) / len(words) if words else 0.0)
    return IntentScores(tuple(ids), np.concatenate([best, np.asarray(extra, dtype=np.float32)]), np.asarray(lexical, dtype=np.float32))


def fuse(scores: IntentScores, p: Thresholds) -> np.ndarray:
    """Convex mix of the rescaled embedding score and the lexical score, in [0, 1]: the embedding says what the
    question is about, the lexicon what it names; neither alone is trusted."""
    e = np.clip((scores.embedding - p.e_lo) / (p.e_hi - p.e_lo), 0.0, 1.0)
    return (1.0 - p.lexical_weight) * e + p.lexical_weight * np.clip(scores.lexical, 0.0, 1.0)


def facts_by_intent(fact_ids: Sequence[str]) -> dict[str, tuple[int, ...]]:
    """Intent id -> positions of the facts of this process that answer it."""
    out: dict[str, list[int]] = {}
    for position, fact_id in enumerate(fact_ids):
        if fact_id.startswith(SIGNAL_PREFIX):
            out.setdefault(fact_id, []).append(position)
            out.setdefault(SIGNALS_ID, []).append(position)  # every signal fact answers "which signals"
        elif fact_id in FACT_INTENT:
            out.setdefault(FACT_INTENT[fact_id], []).append(position)
    # signals.none / signals.unavailable answer the generic question only when no signal fired: a process
    # with signals answers it with the signals themselves.
    own = [p for p in out.get(SIGNALS_ID, []) if fact_ids[p].startswith(SIGNAL_PREFIX)]
    if own:
        out[SIGNALS_ID] = own
    return {k: tuple(v) for k, v in out.items()}


@dataclass(frozen=True, slots=True)
class Decision:
    chosen: tuple[int, ...]  # positions of the facts to state (empty: abstain)
    top_intent: str
    reason: str  # "answered" | "below_floor" | "oos" | "absent_fact"


def decide(scores: IntentScores, mapping: Mapping[str, tuple[int, ...]], p: Thresholds) -> Decision:
    fused = fuse(scores, p)
    order = sorted(range(len(fused)), key=lambda i: (-float(fused[i]), i))
    present = [i for i in order if scores.ids[i] != OOS_ID and scores.ids[i] in mapping]
    top = order[0]
    top_id = scores.ids[top]
    if top_id == OOS_ID:
        return Decision((), top_id, "oos")
    best = present[0] if present else None
    if best is None or float(fused[best]) < p.floor:
        return Decision((), top_id, "below_floor")
    oos = [i for i in range(len(fused)) if scores.ids[i] == OOS_ID]
    if oos and float(fused[oos[0]]) + p.oos_margin > float(fused[best]):
        return Decision((), top_id, "oos")
    absent = [i for i in order if scores.ids[i] != OOS_ID and scores.ids[i] not in mapping and not scores.ids[i].startswith(SIGNAL_PREFIX)]
    if absent and float(fused[absent[0]]) + p.absent_margin > float(fused[best]):
        return Decision((), top_id, "absent_fact")
    picked = [best]
    for i in present[1 : p.k]:
        if float(fused[i]) >= p.floor and float(fused[best]) - float(fused[i]) <= p.second_gap:
            picked.append(i)
    chosen: list[int] = []
    for i in picked:
        for position in mapping[scores.ids[i]]:
            if position not in chosen:
                chosen.append(position)
    return Decision(tuple(chosen[:MAX_GROUP_FACTS]), scores.ids[best], "answered")


def fact_scores(scores: IntentScores, fact_ids: Sequence[str], p: Thresholds) -> np.ndarray:
    """A score per fact (its intent's fused score; a signal fact: the better of its own and the generic
    signals intent). Used to rank candidates for a model."""
    fused = fuse(scores, p)
    by_id = {intent_id: float(fused[i]) for i, intent_id in enumerate(scores.ids)}
    out = np.zeros(len(fact_ids), dtype=np.float32)
    for position, fact_id in enumerate(fact_ids):
        if fact_id.startswith(SIGNAL_PREFIX):
            out[position] = max(by_id.get(fact_id, 0.0), by_id.get(SIGNALS_ID, 0.0))
        else:
            out[position] = by_id.get(FACT_INTENT.get(fact_id, ""), 0.0)
    return out
