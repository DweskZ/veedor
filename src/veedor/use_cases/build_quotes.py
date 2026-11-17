"""Select, for every flagged process, up to three quotes from the text the process itself published.

Retrieval with citations, no generation: a passage is shown exactly as published, with its source field,
or not at all. For each process that has at least one risk or context signal and at least one text:

1. every text passes the eligibility pipeline (`domain.quotes.screen`): personal data first, then the
   unsafe-text screen. A passage that fails is never stored; only counts by reason are kept;
2. eligible passages are embedded with the project's local model and ranked by cosine similarity to the
   Spanish topic descriptions (`domain.quotes.topics`) of the signals that fired on that process;
3. an enquiry is one item: its question, plus the entity's answer as the paired quote when the answer is
   eligible. Items under the similarity floor are not shown (counted as ``below_floor``); items that are
   near-duplicates of an already chosen one are skipped; at most `MAX_QUOTES` items are kept.

Similarity is a ranking aid, not a finding: the quote is context for a signal, never proof of it.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from veedor.domain.masking import is_masked_party, is_natural_person
from veedor.domain.quotes.deny import passage_key
from veedor.domain.quotes.lexicon import Lexicon
from veedor.domain.quotes.screen import PERSONAL, UNSAFE, Verdict, check_passage
from veedor.domain.quotes.topics import SIGNAL_TOPICS_ES

QUESTION = "enquiry_question"
ANSWER = "enquiry_answer"
AWARD_TEXT = "award_text"

MAX_QUOTES = 3
# Items with a paired answer rank slightly higher: a question without its answer is half a statement.
PAIR_BONUS = 0.03
NEAR_DUPLICATE = 0.92  # cosine between the primary passages of two items
# A shown passage is whole when it has at most this many characters (about 90 % of real enquiry questions
# and answers); a longer one is cut at the end of a sentence or clause, never in the middle of one.
QUOTE_MAX_CHARS = 800
EMBED_MAX_CHARS = 1_000
# Smallest step of 0.05 at which passages at or above it are at least twice as likely as all passages to
# contain a deadline or price stem (calibration sample: the first 6,000 flagged processes by ocid; see
# docs/QUOTES.md). The evaluation excludes that sample.
SIMILARITY_FLOOR = 0.35
BATCH_PROCESSES = 2_000


@dataclass(frozen=True, slots=True)
class TextRow:
    kind: str
    seq: int
    text: str
    date: str | None
    author_kind: str
    source_field: str
    truncated: bool
    author_person: bool


@dataclass(frozen=True, slots=True)
class ProcessBundle:
    ocid: str
    signals: tuple[str, ...]
    texts: tuple[TextRow, ...]
    person_names: tuple[str, ...] = ()
    protected_names: tuple[str, ...] = ()


class EmbeddingPort(Protocol):
    """Unit-length float32 vectors, one row per text, same order (the vector index uses the same port)."""

    def embed(self, texts: Sequence[str]) -> np.ndarray: ...


class BundleSource(Protocol):
    def bundles(self, limit: int | None = None) -> Iterator[ProcessBundle]: ...

    def name_vocabulary(self) -> frozenset[str]:
        """Person-name tokens found in the data (see `domain.quotes.names`)."""
        ...

    def lexicon(self) -> Lexicon:
        """Institutional and ordinary vocabulary found in the data (see `domain.quotes.lexicon`)."""
        ...


class QuoteSink(Protocol):
    def write_vocabulary(self, tokens: Sequence[str]) -> None: ...

    def write_lexicon(self, lexicon: Lexicon) -> None: ...

    def write(self, quotes: Sequence[dict[str, Any]], stats: Sequence[dict[str, Any]]) -> None: ...

    def close(self) -> None: ...


# ------------------------------------------------------------------------------- names of a process


def name_context(
    parties: Iterable[tuple[str | None, str | None, str | None]],
    buyer_ruc: str | None,
    buyer_name: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(person_names, protected_names)`` from ``(ruc, name, kind)`` parties: the same rule as
    `queries.processes.name_context` (a natural person or a party without a legal-entity marker is a
    person; every other party and a non-person buyer is protected)."""
    persons: set[str] = set()
    protected: set[str] = set()
    for ruc, name, kind in parties:
        if not name or not name.strip():
            continue
        (persons if is_masked_party(ruc, name, kind) else protected).add(name.strip())
    if buyer_name and buyer_name.strip():
        (persons if is_natural_person(buyer_ruc) else protected).add(buyer_name.strip())
    return tuple(sorted(persons)), tuple(sorted(protected))


# ------------------------------------------------------------------------------------ display text


_SENTENCE_END = re.compile(r"[.!?][\"'»)\]]*(?=\s|$)")
_CLAUSE_END = re.compile(r"[;:,](?=\s)")
_SENTENCE_MIN_SHARE = 0.4  # a sentence cut must keep at least this share of the cap
_CLAUSE_MIN_SHARE = 0.6


def shorten(text: str, limit: int = QUOTE_MAX_CHARS) -> tuple[str, bool]:
    """The text as shown: whole when it has at most `limit` characters, else cut at the last sentence end
    inside the limit, else at the last clause end (`;` `:` `,`), else at a word. The cut carries no
    ellipsis: the flag says it was cut and the page writes the mark. A text is never cut mid-sentence
    when a sentence end exists in the second part of the window."""
    if len(text) <= limit:
        return text, False
    window = text[:limit]
    for pattern, share in ((_SENTENCE_END, _SENTENCE_MIN_SHARE), (_CLAUSE_END, _CLAUSE_MIN_SHARE)):
        ends = [m.end() for m in pattern.finditer(window) if m.end() >= limit * share]
        if ends:
            return window[: ends[-1]].rstrip(" ,;:"), True
    boundary = window.rfind(" ")
    return (window[:boundary] if boundary > limit // 2 else window).rstrip(" ,;:."), True


# ----------------------------------------------------------------------------------- eligibility


@dataclass(slots=True)
class Judged:
    row: TextRow
    verdict: Verdict


def judge_texts(
    bundle: ProcessBundle,
    name_vocabulary: frozenset[str] = frozenset(),
    lexicon: Lexicon | None = None,
) -> list[Judged]:
    """Eligibility of every text. An answer inherits the exclusion of its question: an exchange whose
    question is withheld is withheld whole (the answer can address or quote the asker)."""
    verdicts: dict[tuple[str, int], Verdict] = {}
    judged: list[Judged] = []
    ordered = sorted(bundle.texts, key=lambda r: (r.kind == ANSWER, r.seq))
    for row in ordered:
        if row.kind == ANSWER and not (question := verdicts.get((QUESTION, row.seq), Verdict(True))).eligible:
            verdict = Verdict(False, question.category, "question_excluded")
        else:
            verdict = check_passage(
                row.text,
                person_names=bundle.person_names,
                protected_names=bundle.protected_names,
                asker_is_person=row.author_person,
                name_vocabulary=name_vocabulary,
                lexicon=lexicon,
            )
            shown_text = shorten(row.text)[0]
            if verdict.eligible and shown_text != row.text:
                # a cut passage is what is stored and shown: it must pass on its own (a cut can change the
                # share of capitals or open a sentence with an unknown word)
                verdict = check_passage(
                    shown_text,
                    person_names=bundle.person_names,
                    protected_names=bundle.protected_names,
                    asker_is_person=row.author_person,
                    name_vocabulary=name_vocabulary,
                    lexicon=lexicon,
                )
        verdicts[(row.kind, row.seq)] = verdict
        judged.append(Judged(row, verdict))
    return judged


# -------------------------------------------------------------------------------------- selection


@dataclass(slots=True)
class Item:
    primary: TextRow
    pair: TextRow | None
    members: list[TextRow]
    score: float
    signal: str
    best_member: TextRow


def _items(
    eligible: dict[tuple[str, int], TextRow], scores: dict[tuple[str, int], tuple[float, str]]
) -> list[Item]:
    items: list[Item] = []
    for seq in sorted({s for _, s in eligible}):
        question = eligible.get((QUESTION, seq))
        answer = eligible.get((ANSWER, seq))
        members = [m for m in (question, answer) if m is not None]
        if members:
            best = max(members, key=lambda m: scores[(m.kind, m.seq)][0])
            score, signal = scores[(best.kind, best.seq)]
            primary = question or answer
            items.append(Item(primary, answer if question and answer else None, members, score, signal, best))
    for (kind, seq), row in sorted(eligible.items()):
        if kind == AWARD_TEXT:
            score, signal = scores[(kind, seq)]
            items.append(Item(row, None, [row], score, signal, row))
    return items


@dataclass(slots=True)
class ProcessResult:
    quotes: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    reasons: Counter[str] = field(default_factory=Counter)
    near_duplicates: int = 0
    repeated: int = 0


@dataclass(frozen=True, slots=True)
class Shown:
    """The passages of an item as they would be displayed."""

    text: str
    cut: bool
    pair_text: str | None
    pair_cut: bool

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(passage_key(t) for t in (self.text, self.pair_text) if t)


def shown(item: Item) -> Shown:
    """The displayed passages. An answer that repeats its question word for word is not shown twice."""
    text, cut = shorten(item.primary.text)
    pair_text, pair_cut = shorten(item.pair.text) if item.pair is not None else (None, False)
    if pair_text is not None and passage_key(pair_text) == passage_key(text):
        pair_text, pair_cut = None, False
    return Shown(text, cut, pair_text, pair_cut)


def _quote_row(ocid: str, rank: int, item: Item, view: Shown) -> dict[str, Any]:
    return {
        "ocid": ocid,
        "rank": rank,
        "kind": item.primary.kind,
        "text": view.text,
        "date": item.primary.date,
        "author_kind": item.primary.author_kind,
        "source_field": item.primary.source_field,
        "related_signal": item.signal,
        "similarity": round(float(item.score), 4),
        "truncated": bool(item.primary.truncated or view.cut),
        "pair_text": view.pair_text,
        "pair_kind": item.pair.kind if view.pair_text is not None and item.pair else None,
        "pair_source_field": item.pair.source_field if view.pair_text is not None and item.pair else None,
        "pair_truncated": bool(
            view.pair_text is not None and item.pair and (item.pair.truncated or view.pair_cut)
        ),
    }


def select_for_process(
    bundle: ProcessBundle,
    judged: Sequence[Judged],
    vectors: dict[str, np.ndarray],
    topic_codes: Sequence[str],
    topic_matrix: np.ndarray,
    floor: float = SIMILARITY_FLOOR,
) -> ProcessResult:
    """Rank the eligible passages of one process and keep the best items (see the module docstring)."""
    result = ProcessResult()
    counts = Counter(j.verdict.category for j in judged if not j.verdict.eligible)
    result.reasons.update(
        f"{j.verdict.category}:{j.verdict.reason}" for j in judged if not j.verdict.eligible
    )
    fired = [i for i, code in enumerate(topic_codes) if code in bundle.signals]
    eligible = {(j.row.kind, j.row.seq): j.row for j in judged if j.verdict.eligible}
    below = 0
    chosen: list[tuple[Item, Shown]] = []
    used: set[str] = set()  # a passage is shown at most once per process, as an item or as a pair
    if eligible and fired:
        keys = list(eligible)
        matrix = np.vstack([vectors[eligible[k].text[:EMBED_MAX_CHARS]] for k in keys])
        sims = matrix @ topic_matrix[fired].T
        scores = {
            key: (float(sims[i].max()), topic_codes[fired[int(sims[i].argmax())]])
            for i, key in enumerate(keys)
        }
        items = _items(eligible, scores)
        above = [item for item in items if item.score >= floor]
        below = sum(len(item.members) for item in items if item.score < floor)
        above.sort(
            key=lambda it: (-(it.score + (PAIR_BONUS if it.pair else 0.0)), it.primary.kind, it.primary.seq)
        )
        for item in above:
            if len(chosen) == MAX_QUOTES:
                break
            view = shown(item)
            if used.intersection(view.keys):
                result.repeated += 1
                continue
            vec = vectors[item.primary.text[:EMBED_MAX_CHARS]]
            if any(
                float(vec @ vectors[c.primary.text[:EMBED_MAX_CHARS]]) >= NEAR_DUPLICATE for c, _ in chosen
            ):
                result.near_duplicates += 1
                continue
            used.update(view.keys)
            chosen.append((item, view))
    elif eligible:
        below = len(eligible)  # no signal with a topic fired: nothing to rank against
    result.quotes = [_quote_row(bundle.ocid, rank, i, v) for rank, (i, v) in enumerate(chosen, 1)]
    result.stats = {
        "ocid": bundle.ocid,
        "available_total": len(bundle.texts),
        "excluded_personal": counts.get(PERSONAL, 0),
        "excluded_unsafe": counts.get(UNSAFE, 0),
        "below_floor": below,
        "n_eligible": len(eligible),
        "n_quotes": len(chosen),
    }
    return result


# ------------------------------------------------------------------------------------------ build


@dataclass(slots=True)
class QuotesReport:
    processes: int = 0
    processes_with_quote: int = 0
    texts: int = 0
    quotes: int = 0
    pairs: int = 0
    near_duplicates: int = 0
    repeated: int = 0
    reasons: Counter[str] = field(default_factory=Counter)
    by_signal_processes: Counter[str] = field(default_factory=Counter)
    by_signal_with_quote: Counter[str] = field(default_factory=Counter)
    by_signal_quotes: Counter[str] = field(default_factory=Counter)
    embed_seconds: float = 0.0
    wall_seconds: float = 0.0
    embedded_texts: int = 0
    name_vocabulary: int = 0
    lexicon_capitalised: int = 0
    lexicon_lowercase: int = 0
    floor: float = SIMILARITY_FLOOR

    @property
    def processes_per_second(self) -> float:
        return self.processes / self.wall_seconds if self.wall_seconds else 0.0

    @property
    def texts_per_second(self) -> float:
        return self.texts / self.wall_seconds if self.wall_seconds else 0.0


def topic_vectors(embedder: EmbeddingPort) -> tuple[list[str], np.ndarray]:
    codes = sorted(SIGNAL_TOPICS_ES)
    return codes, embedder.embed([SIGNAL_TOPICS_ES[c] for c in codes])


def _batches(source: BundleSource, limit: int | None, size: int) -> Iterator[list[ProcessBundle]]:
    batch: list[ProcessBundle] = []
    for bundle in source.bundles(limit):
        batch.append(bundle)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def build_quotes(
    source: BundleSource,
    embedder: EmbeddingPort,
    sink: QuoteSink,
    *,
    limit: int | None = None,
    floor: float = SIMILARITY_FLOOR,
    batch_size: int = BATCH_PROCESSES,
    progress: Callable[[QuotesReport], None] | None = None,
) -> QuotesReport:
    """Run the whole selection. Idempotent: the result depends only on the inputs and the model."""
    started = time.perf_counter()
    report = QuotesReport(floor=floor)
    codes, topics = topic_vectors(embedder)
    vocabulary = source.name_vocabulary()
    report.name_vocabulary = len(vocabulary)
    sink.write_vocabulary(sorted(vocabulary))
    lexicon = source.lexicon()
    report.lexicon_capitalised = len(lexicon.capitalised)
    report.lexicon_lowercase = len(lexicon.lowercase)
    sink.write_lexicon(lexicon)
    for batch in _batches(source, limit, batch_size):
        judged_by_ocid = {b.ocid: judge_texts(b, vocabulary, lexicon) for b in batch}
        unique = sorted(
            {
                j.row.text[:EMBED_MAX_CHARS]
                for judged in judged_by_ocid.values()
                for j in judged
                if j.verdict.eligible
            }
        )
        t0 = time.perf_counter()
        matrix = embedder.embed(unique) if unique else np.zeros((0, topics.shape[1]), dtype=np.float32)
        report.embed_seconds += time.perf_counter() - t0
        report.embedded_texts += len(unique)
        vectors = dict(zip(unique, matrix, strict=True))
        quotes: list[dict[str, Any]] = []
        stats: list[dict[str, Any]] = []
        for bundle in batch:
            result = select_for_process(bundle, judged_by_ocid[bundle.ocid], vectors, codes, topics, floor)
            quotes.extend(result.quotes)
            stats.append(result.stats)
            _count(report, bundle, result)
        sink.write(quotes, stats)
        report.wall_seconds = time.perf_counter() - started
        if progress:
            progress(report)
    sink.close()
    report.wall_seconds = time.perf_counter() - started
    return report


def _count(report: QuotesReport, bundle: ProcessBundle, result: ProcessResult) -> None:
    report.processes += 1
    report.texts += len(bundle.texts)
    report.quotes += len(result.quotes)
    report.pairs += sum(1 for q in result.quotes if q["pair_text"])
    report.near_duplicates += result.near_duplicates
    report.repeated += result.repeated
    report.reasons.update(result.reasons)
    has_quote = bool(result.quotes)
    report.processes_with_quote += has_quote
    for code in set(bundle.signals):
        report.by_signal_processes[code] += 1
        report.by_signal_with_quote[code] += has_quote
    report.by_signal_quotes.update(q["related_signal"] for q in result.quotes)
