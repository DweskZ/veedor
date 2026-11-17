"""Question answering over one process: screen, retrieve, select, render, verify.

The model never writes prose. The only text an answer can hold is a fixed sentence, a sentence the dossier
renderer wrote for a fact of this process, or a stored quote shown verbatim:

    question -> screen -> retrieve (embeddings) -> select (model picks ids, or top-k) -> render -> verify

The question is untrusted text. It is embedded, and sent to the model as a JSON string inside a data block;
it is never used as SQL, a path, a URL, a tool argument or a template, and only a salted hash, its length and
the outcome are ever logged (`veedor.ask` logger) or put in a metric.
"""

from __future__ import annotations

import logging
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

import numpy as np

from veedor.agents.qa.selector import ModelSelector
from veedor.domain.dossier.grounding import verify
from veedor.domain.dossier.models import EvidencePack
from veedor.domain.dossier.text import strip_accents
from veedor.domain.qa.answer import (
    ANSWERED_NOTE_ES,
    MODE_MODEL,
    MODE_RETRIEVAL,
    Answer,
    QuotedPassage,
    Reason,
    Sentence,
    fixed_answer,
)
from veedor.domain.qa.facts import QaFact
from veedor.domain.qa.screen import (
    Fingerprint,
    Intent,
    Problem,
    classify_question,
    fingerprint,
    normalise_for_key,
    validate_question,
)
from veedor.domain.qa.selection import (
    DEFAULT_THRESHOLDS,
    Thresholds,
    retrieval_select,
    similarity_scores,
    top_indices,
)

logger = logging.getLogger("veedor.ask")
EMBED_CHARS = 600
CACHE_ENTRIES = 512


class InvalidQuestionError(ValueError):
    """The question is not well formed. Carries the closed reason; never the question."""

    def __init__(self, problem: Problem) -> None:
        super().__init__(problem.value)
        self.problem = problem


class EmbeddingPort(Protocol):
    def embed(self, texts: Sequence[str]) -> np.ndarray: ...


@dataclass(frozen=True, slots=True)
class StoredQuote:
    """One stored quote item (a passage, with its paired answer when there is one)."""

    rank: int
    passages: tuple[QuotedPassage, ...]


@dataclass(frozen=True, slots=True)
class ProcessContext:
    pack: EvidencePack
    facts: list[QaFact]
    quotes: list[StoredQuote]
    data_version: str


class ContextLoader(Protocol):
    def load(self, ocid: str) -> ProcessContext:
        """Raises `NotFoundError` (or any exception) when the process cannot be loaded."""
        ...


class UsageStore(Protocol):
    """Counters shared by every worker and kept across restarts (the database)."""

    def consume(self, bucket: str, limit: int) -> bool: ...

    def used(self, bucket: str) -> int: ...


class DailyBudget:
    """Model calls allowed per UTC day.

    With a shared `store` the day's count lives in the database: the same for every worker, kept across a
    restart. Without one (tests, no database), or when the store fails, the budget falls back to an in-memory
    count of `fallback_limit` calls for this worker only (reset on restart): the caller sets it to the share
    of one worker so the workers together still stay within the global limit."""

    def __init__(
        self,
        limit: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        *,
        store: UsageStore | None = None,
        fallback_limit: int | None = None,
    ) -> None:
        self.limit = limit
        self._clock = clock
        self._store = store
        self._fallback_limit = limit if fallback_limit is None else fallback_limit
        self._day = clock().date()
        self._used = 0

    def try_consume(self) -> bool:
        today = self._clock().date()
        if self._store is not None:
            try:
                return self._store.consume(f"budget:{today.isoformat()}", self.limit)
            except Exception:  # noqa: BLE001 - a database problem must not switch the budget off
                logger.warning("shared ask budget unavailable; counting in memory for this worker")
        if today != self._day:
            self._day, self._used = today, 0
        if self._used >= self._fallback_limit:
            return False
        self._used += 1
        return True

    @property
    def remaining(self) -> int:
        return max(self.limit - self._used, 0) if self._clock().date() == self._day else self.limit


@dataclass
class AskCounters:
    """Process-wide counters (no text): what the evaluation and the logs report."""

    questions: int = 0
    rejected: int = 0
    model_calls: int = 0
    model_failures: int = 0
    invalid_replies: int = 0
    discarded_ids: int = 0
    budget_exhausted: int = 0
    grounding_failures: int = 0
    cache_hits: int = 0


@dataclass
class AskService:
    loader: ContextLoader
    embedder: EmbeddingPort
    selector: ModelSelector | None = None
    thresholds: Thresholds = DEFAULT_THRESHOLDS
    budget: DailyBudget | None = None
    observer: Callable[[Answer, float], None] | None = None
    salt: bytes = field(default_factory=lambda: secrets.token_bytes(16))
    counters: AskCounters = field(default_factory=AskCounters)
    _cache: OrderedDict[tuple, Answer] = field(default_factory=OrderedDict)

    # --- public -----------------------------------------------------------------------------------------

    def ask(self, ocid: str, raw_question: str) -> Answer:
        started = time.perf_counter()
        screened = validate_question(raw_question)
        if not screened.ok:
            self.counters.rejected += 1
            self._audit(ocid, fingerprint(raw_question[:600], self.salt), f"rejected:{screened.problem}", "-")
            assert screened.problem is not None
            raise InvalidQuestionError(screened.problem)
        self.counters.questions += 1
        text = screened.text
        trace = fingerprint(text, self.salt)
        intent = classify_question(text)
        if intent is not Intent.ANSWERABLE:
            answer = fixed_answer(ocid, Reason(intent.value))
            return self._finish(answer, trace, started)
        context = self.loader.load(ocid)
        use_model = self.selector is not None
        key = (ocid, normalise_for_key(text), context.data_version, use_model)
        if key in self._cache:
            self._cache.move_to_end(key)
            self.counters.cache_hits += 1
            cached = self._cache[key]
            return self._finish(_copy(cached, cached=True), trace, started)
        answer = self._answer(ocid, text, context)
        self._cache[key] = _copy(answer)
        while len(self._cache) > CACHE_ENTRIES:
            self._cache.popitem(last=False)
        return self._finish(answer, trace, started)

    # --- internals --------------------------------------------------------------------------------------

    def _answer(self, ocid: str, text: str, context: ProcessContext) -> Answer:
        facts = context.facts
        if not facts:
            return fixed_answer(ocid, Reason.NO_EVIDENCE)
        query = self.embedder.embed(_variants(text))
        fact_scores = self._fact_scores(query, facts)
        chosen: list[int] | None = None
        mode, usage = MODE_RETRIEVAL, (0, 0, 0, 0)
        best = float(max(fact_scores)) if len(fact_scores) else 0.0
        if self.selector is not None and best >= self.thresholds.model_floor:
            chosen, usage = self._ask_model(text, facts, fact_scores)
            if chosen is not None:
                mode = MODE_MODEL
        if chosen is None:
            chosen = retrieval_select(fact_scores, self.thresholds)
        if not chosen:
            answer = fixed_answer(ocid, Reason.NO_EVIDENCE, mode)
            return _with_usage(answer, usage)
        answer = self._render(ocid, mode, [facts[i] for i in sorted(chosen)], context, query)
        answer = _with_usage(answer, usage)
        text_out = "\n".join(s.text for s in answer.sentences)
        report = verify(text_out, context.pack)
        answer.grounded = report.passed
        if not report.passed:
            self.counters.grounding_failures += 1
            failed = fixed_answer(ocid, Reason.UNVERIFIED, mode)
            failed.grounded = False
            return _with_usage(failed, usage)
        return answer

    def score_facts(self, context: ProcessContext, text: str) -> np.ndarray:
        """Similarity of a screened question to every fact of the context (used by the evaluation to tune
        thresholds without asking the same question once per setting)."""
        return self._fact_scores(self.embedder.embed(_variants(text)), context.facts)

    def _fact_scores(self, query: np.ndarray, facts: list[QaFact]) -> np.ndarray:
        """Per fact, the best similarity of the question to any of its key phrases or to its sentence."""
        phrases = [(i, p) for i, f in enumerate(facts) for p in f.key_phrases]
        owner = np.array([i for i, _ in phrases], dtype=int)
        by_phrase = similarity_scores(query, self.embedder.embed([p for _, p in phrases]))
        scores = similarity_scores(query, self.embedder.embed([f.text[:EMBED_CHARS] for f in facts]))
        np.maximum.at(scores, owner, by_phrase)
        return scores

    def _ask_model(
        self, text: str, facts: list[QaFact], scores: np.ndarray
    ) -> tuple[list[int] | None, tuple[int, int, int, int]]:
        """``(chosen indices, usage)``: ``[]`` means the model says nothing answers; ``None`` means the
        model was not used or its reply was not valid, so retrieval decides."""
        assert self.selector is not None
        if self.budget is not None and not self.budget.try_consume():
            self.counters.budget_exhausted += 1
            return None, (0, 0, 0, 0)
        order = top_indices(scores, self.thresholds.candidates)
        candidates = [facts[i] for i in sorted(order)]
        self.counters.model_calls += 1
        result = self.selector.select(text, candidates)
        usage = (1, result.prompt_tokens, result.completion_tokens, result.choice.discarded)
        self.counters.discarded_ids += result.choice.discarded
        if result.failed:
            self.counters.model_failures += 1
            return None, usage
        if not result.choice.valid:
            self.counters.invalid_replies += 1
            return None, usage
        position = {f.fact_id: i for i, f in enumerate(facts)}
        if not result.choice.answerable:
            return [], usage
        return [position[i] for i in result.choice.fact_ids], usage

    def _render(
        self, ocid: str, mode: str, chosen: list[QaFact], context: ProcessContext, query: np.ndarray
    ) -> Answer:
        sentences = [Sentence(f.text, f.fact_id, f.source_id, f.source_field) for f in chosen]
        quotes = self._attach_quotes(context.quotes, query)
        return Answer(
            ocid=ocid,
            answerable=True,
            mode=mode,
            reason=Reason.ANSWERED,
            sentences=sentences,
            quotes=quotes,
            note_es=ANSWERED_NOTE_ES,
        )

    def _attach_quotes(self, stored: list[StoredQuote], query: np.ndarray) -> list[QuotedPassage]:
        """Stored quotes whose passages are close to the question. By similarity alone: no model sees them."""
        if not stored:
            return []
        passages = [p for item in stored for p in item.passages]
        matrix = self.embedder.embed([p.text[:EMBED_CHARS] for p in passages])
        scores = similarity_scores(query, matrix)
        out: list[tuple[float, StoredQuote]] = []
        start = 0
        for item in stored:
            n = len(item.passages)
            out.append((float(scores[start : start + n].max()), item))
            start += n
        out.sort(key=lambda pair: (-pair[0], pair[1].rank))
        picked = [item for score, item in out if score >= self.thresholds.quote_floor]
        return [p for item in picked[: self.thresholds.max_quotes] for p in item.passages]

    def _finish(self, answer: Answer, trace: Fingerprint, started: float) -> Answer:
        self._audit(answer.ocid, trace, answer.reason.value, answer.mode)
        if self.observer is not None:
            try:
                self.observer(answer, (time.perf_counter() - started) * 1000)
            except Exception:  # noqa: BLE001 - observability never breaks an answer
                logger.debug("observer failed")
        return answer

    @staticmethod
    def _audit(ocid: str, trace: Fingerprint, outcome: str, mode: str) -> None:
        """The only record of a question: a salted hash, its length, the outcome. Never the text."""
        logger.info(
            "ask ocid=%s qhash=%s qlen=%d outcome=%s mode=%s", ocid, trace.digest, trace.length, outcome, mode
        )


def _variants(text: str) -> list[str]:
    """The question as written and without accents: informal spelling often drops them."""
    plain = strip_accents(text)
    return [text] if plain == text else [text, plain]


def _copy(answer: Answer, *, cached: bool = False) -> Answer:
    return Answer(
        ocid=answer.ocid,
        answerable=answer.answerable,
        mode=answer.mode,
        reason=answer.reason,
        sentences=list(answer.sentences),
        quotes=list(answer.quotes),
        note_es=answer.note_es,
        discarded_ids=answer.discarded_ids,
        model_calls=0 if cached else answer.model_calls,
        prompt_tokens=0 if cached else answer.prompt_tokens,
        completion_tokens=0 if cached else answer.completion_tokens,
        grounded=answer.grounded,
        cached=cached,
    )


def _with_usage(answer: Answer, usage: tuple[int, int, int, int]) -> Answer:
    answer.model_calls, answer.prompt_tokens, answer.completion_tokens, answer.discarded_ids = usage
    return answer
