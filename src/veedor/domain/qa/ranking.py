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

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from veedor.domain.qa.intents import (
    FACT_INTENTS,
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

RETRIEVAL_VERSION = "intents-v2"  # intents-v1: the first intent retrieval (docs/EVALUATION.md measured it on held-out 1)
MAX_GROUP_FACTS = 8  # a signals question is answered with every signal fact, up to this many


# Words a question uses whatever it is about (question words, pronouns, light verbs, fillers). Not evidence either way.
FRAME_WORDS = frozenset(
    "cual cuales cuanto cuanta cuantos cuantas quien quienes como cuando donde porque para esto esta este estos estas esos esas "
    "hubo tiene tienen tenia tuvo fue fueron hizo hacen hace sido siendo sobre entre desde hasta mas menos muy tambien ademas pero "
    "solo oiga oye dime dame diga quiero quisiera saber necesito podria puedes puede favor hola gracias entonces ahora aqui alli ahi "
    "algun alguna algunos algunas alguien cada todo toda todos todas otro otra otros otras mismo misma estan estaba estar ese esa "
    "tipo cosa cosas manera forma parte lado dato datos informacion detalle detalles hay existe existen sera seria sigue sino "
    "vez veces tanto tanta cuyo donde ellos ellas nosotros usted ustedes nada algo mucho mucha muchos muchas poco poca pocos "
    "pues bueno digame mire vea ver decir dicen dijo quedo queda quedaron llama llaman llamado llamada seguro verdad cierto "
    "claro exacto exactamente aproximadamente realmente solo solamente siempre nunca jamas aun todavia ademas incluso".split()
)
NOUN_CUES = frozenset(
    "de del en a al para por con sobre desde hasta el la los las un una unos unas mi tu su sus este esta ese esa estos esos "
    "mas otro otra otros otras primer primera ultimo ultima".split()
)
FOREIGN_FLOOR = 0.5  # cosine of a word to its nearest domain word below which the word is foreign
MIN_WORD = 4


class IntentIndex:
    """The prototype embeddings of every static intent, built once from an embedder, and the vocabulary of the domain
    (every word of the in-scope prototypes, keys, lexicon and signal labels) with its embeddings: the reference
    against which the words of a question are judged foreign or not."""

    def __init__(self, embed: Callable[[Sequence[str]], np.ndarray]) -> None:
        self._embed = embed
        words: set[str] = set()
        from veedor.domain.signals import SIGNALS_BY_CODE

        for spec in INTENTS:
            if spec.id == OOS_ID:
                continue
            for phrase in key_phrases_of(spec):
                words |= set(fold_text(phrase).split())
            for term, _ in spec.terms:
                words |= set(fold_text(term.replace("~", " ").replace("*", "")).split())
        for definition in SIGNALS_BY_CODE.values():
            words |= set(fold_text(f"{definition.label_es} {definition.description_es}").split())
        self.domain_words = frozenset(w for w in words if len(w) >= MIN_WORD)
        ordered = sorted(self.domain_words)
        self.word_matrix = embed(ordered) if ordered else np.zeros((0, 0), dtype=np.float32)
        self._word_cache: dict[str, float] = {}
        self.ids: tuple[str, ...] = tuple(spec.id for spec in INTENTS)
        phrases: list[str] = []
        owner: list[int] = []
        for position, spec in enumerate(INTENTS):
            for phrase in dict.fromkeys(p for raw in key_phrases_of(spec) for p in embedding_variants(raw)):
                phrases.append(phrase)
                owner.append(position)
        self.owner = np.asarray(owner, dtype=int)
        self.matrix = embed(phrases) if phrases else np.zeros((0, 0), dtype=np.float32)


    def foreign_share(self, text: str) -> float:
        """Share of the content words of `text` that are foreign to the domain. A word counts when it stands where a
        noun or a name stands (after a preposition or a determiner: "de francia", "un taxi"), is not a frame word, is
        not in the domain vocabulary and is far (cosine below `FOREIGN_FLOOR`) from every domain word. Verbs, adverbs
        and fillers ("estamos hablando de", "harta competencia") are not evidence. 0 when there is no content word."""
        tokens = fold_text(text).split()
        content = [
            (i, w) for i, w in enumerate(tokens) if len(w) >= MIN_WORD and w not in FRAME_WORDS
        ]
        if not content:
            return 0.0
        unknown = list(dict.fromkeys(w for _, w in content if w not in self.domain_words and w not in self._word_cache))
        if unknown and self.word_matrix.shape[0]:
            vectors = self._embed(unknown)
            for word, best in zip(unknown, (vectors @ self.word_matrix.T).max(axis=1), strict=True):
                self._word_cache[word] = float(best)
        foreign = sum(
            1
            for i, w in content
            if w not in self.domain_words and self._word_cache.get(w, 1.0) < FOREIGN_FLOOR and i > 0 and tokens[i - 1] in NOUN_CUES
        )
        return foreign / len({w for _, w in content})


@dataclass(frozen=True, slots=True)
class IntentScores:
    """Per intent: best cosine to a prototype and lexical score. Static intents first, then one entry per
    signal fact of the process (`signal:CODE`, embedding only)."""

    ids: tuple[str, ...]
    embedding: np.ndarray
    lexical: np.ndarray
    foreign: float = 0.0  # share of the question's content words that are foreign to the domain


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
    return IntentScores(
        tuple(ids), np.concatenate([best, np.asarray(extra, dtype=np.float32)]), np.asarray(lexical, dtype=np.float32), index.foreign_share(text)
    )


def fuse(scores: IntentScores, p: Thresholds) -> np.ndarray:
    """Convex mix of the rescaled embedding score and the lexical score, in [0, 1]: the embedding says what the
    question is about, the lexicon what it names; neither alone is trusted."""
    e = np.clip((scores.embedding - p.e_lo) / (p.e_hi - p.e_lo), 0.0, 1.0)
    lexical = np.clip(scores.lexical, 0.0, 1.0)
    fused = (1.0 - p.lexical_weight) * e + p.lexical_weight * lexical
    if scores.foreign > 0.0:
        # Foreign words say "this is about something else": they raise the out-of-scope lexical evidence and lower the
        # evidence of every in-scope intent, so one shared word cannot carry the answer.
        oos = np.asarray([i == OOS_ID for i in scores.ids])
        boosted = 1.0 - (1.0 - lexical) * (1.0 - min(1.0, p.foreign_oos * scores.foreign))
        fused = np.where(oos, (1.0 - p.lexical_weight) * e + p.lexical_weight * boosted, fused * (1.0 - p.foreign_penalty * scores.foreign))
    return fused


def facts_by_intent(fact_ids: Sequence[str]) -> dict[str, tuple[int, ...]]:
    """Intent id -> positions of the facts of this process that answer it."""
    out: dict[str, list[int]] = {}
    for position, fact_id in enumerate(fact_ids):
        if fact_id.startswith(SIGNAL_PREFIX):
            out.setdefault(fact_id, []).append(position)
            out.setdefault(SIGNALS_ID, []).append(position)  # every signal fact answers "which signals"
        else:
            for intent_id in FACT_INTENTS.get(fact_id, ()):  # a fact may answer several intents (the comparison one too)
                out.setdefault(intent_id, []).append(position)
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


_JOINERS = re.compile(r"\s*(?:,|;|\by\b|\be\b(?=\s+i)|\bademas\b|\btambien\b|\by tambien\b)\s*", re.IGNORECASE)
MAX_SPLITS = 3


def clause_splits(text: str) -> list[tuple[str, str]]:
    """The ways to read one question as two (at most `MAX_SPLITS`): cut at a "y", "e", comma or "además". Each part must
    hold a word of three letters or more. Beyond two intents nothing is split (one question per call)."""
    out: list[tuple[str, str]] = []
    for match in _JOINERS.finditer(text):
        left, right = text[: match.start()].strip(" ¿?¡!"), text[match.end() :].strip(" ¿?¡!")
        if any(len(w) >= 3 for w in left.split()) and any(len(w) >= 3 for w in right.split()):
            out.append((left, right))
        if len(out) >= MAX_SPLITS:
            break
    return out


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
            out[position] = max((by_id.get(i, 0.0) for i in FACT_INTENTS.get(fact_id, ())), default=0.0)
    return out
