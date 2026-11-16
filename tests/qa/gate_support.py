# ruff: noqa: E501
"""A small fixed question set over the synthetic packs, for the regression gate (retrieval only)."""

from __future__ import annotations

import time

from qa_support import load_pack, make_context, with_investigation  # noqa: F401  (pytest puts this folder on sys.path)

from veedor.domain.qa.selection import Thresholds
from veedor.evaluation.qa import questions as q
from veedor.evaluation.qa.generate import ADVERSARIAL, ANSWERABLE, UNANSWERABLE, EvalQuestion
from veedor.evaluation.qa.metrics import Outcome, ProcessText, summarise
from veedor.use_cases.ask import AskService, InvalidQuestionError


def fixed_questions(contexts) -> list[EvalQuestion]:
    """The first phrasing of every fact type for every context that has the fact, the first two unanswerable
    questions of every group and every attack: no randomness, so the gate never moves by itself."""
    out: list[EvalQuestion] = []
    for ocid, ctx in contexts.items():
        have = {f.fact_id for f in ctx.facts}
        company = bool(ctx.pack.winner and ctx.pack.winner.kind in ("company", "public_entity"))
        for t in [*q.ANSWERABLE, *q.INVESTIGATION]:
            if set(t.expected) <= have and (company or not t.needs_company_winner):
                out.append(EvalQuestion(ocid, t.phrasings[0], ANSWERABLE, t.name, t.expected))
        for tag, pool in (("not_in_the_data", q.NOT_IN_THE_DATA), ("off_topic", q.OFF_TOPIC)):
            out += [EvalQuestion(ocid, text, UNANSWERABLE, tag) for text in pool[:3]]
    first = next(iter(contexts))
    out += [EvalQuestion(first, text, ADVERSARIAL, cat, attack=i) for i, (cat, text) in enumerate(q.ATTACKS)]
    return out


def run_gate(contexts, embedder, thresholds: Thresholds) -> dict:
    class Loader:
        def load(self, ocid):
            return contexts[ocid]

    service = AskService(Loader(), embedder, None, thresholds)
    outcomes = []
    for item in fixed_questions(contexts):
        started = time.perf_counter()
        try:
            answer, rejected = service.ask(item.ocid, item.text), None
        except InvalidQuestionError as exc:
            answer, rejected = None, exc.problem.value
        outcomes.append(Outcome(item, answer, (time.perf_counter() - started) * 1000, rejected))
    texts = {
        ocid: ProcessText({f.fact_id: f.text for f in c.facts}, frozenset(p.text for i in c.quotes for p in i.passages), (), ())
        for ocid, c in contexts.items()
    }
    return summarise(outcomes, texts, model=False)
