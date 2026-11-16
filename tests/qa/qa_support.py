# ruff: noqa: E501
"""Shared pieces of the question-answering tests: synthetic contexts, fake embedder and a scripted model."""

from __future__ import annotations

import json
from pathlib import Path

from veedor.agents.qa.selector import ModelSelector
from veedor.domain.dossier.models import EnquiriesFacts, EvidencePack, InvestigationFacts, PairHistoryFacts
from veedor.domain.qa.answer import QuotedPassage
from veedor.domain.qa.facts import QaFact, build_facts
from veedor.domain.qa.selection import Thresholds
from veedor.infrastructure.llm.fake import FakeStructuredModel
from veedor.infrastructure.vectors.embedding import FakeEmbedder
from veedor.use_cases.ask import AskService, DailyBudget, ProcessContext, StoredQuote

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dossier"
# The hashed bag-of-words embedder scores shared words only, far below a real model: a low floor.
FAKE_THRESHOLDS = Thresholds(floor=0.2, k=2, model_floor=0.05, candidates=40, quote_floor=0.2, max_quotes=2)

SAFE_QUOTE = "Se solicita ampliar el plazo de presentación de ofertas por falta de tiempo"
SAFE_ANSWER = "No se amplía el plazo establecido en el cronograma"


def load_pack(name: str) -> EvidencePack:
    return EvidencePack.model_validate(json.loads((FIXTURES / f"{name}.json").read_text()))


def with_investigation(pack: EvidencePack) -> EvidencePack:
    deadline = pack.process.tender_end or "2023-06-01"
    pack = pack.model_copy(update={"process": pack.process.model_copy(update={"tender_end": deadline, "n_enquiries": 9})})
    facts = InvestigationFacts(
        pair_history=PairHistoryFacts(outcome="ok", n_other_awards=3, n_with_amount=2, total_other_amount=5000.25),
        enquiries=EnquiriesFacts(
            outcome="ok", n_registered=9, n_with_text=8, n_answered=6, n_dated_pairs=5, median_days_to_answer=2.5,
            max_days_to_answer=6, deadline=deadline, late_window_days=3, n_late=2, topic_deadlines=3,
            topic_specifications=2, topic_price=1, topic_requirements=4,
        ),
    )  # fmt: skip
    return pack.model_copy(update={"investigation": facts})


def make_context(pack: EvidencePack, *, quotes: bool = True) -> ProcessContext:
    stored = []
    if quotes:
        stored = [
            StoredQuote(
                1,
                (
                    QuotedPassage("q1", SAFE_QUOTE, "enquiry_question", "2023-05-01", "tender.enquiries[0].description"),
                    QuotedPassage("q1a", SAFE_ANSWER, "enquiry_answer", None, "tender.enquiries[0].answer"),
                ),
            )
        ]
    return ProcessContext(pack, build_facts(pack), stored, "test-build")


class StaticLoader:
    def __init__(self, contexts: dict[str, ProcessContext]) -> None:
        self._contexts = contexts

    def load(self, ocid: str) -> ProcessContext:
        return self._contexts[ocid]


def make_service(context: ProcessContext, replies: list | None = None, *, budget: int | None = None, **kwargs) -> AskService:
    selector = ModelSelector(FakeStructuredModel(replies)) if replies is not None else None
    return AskService(
        StaticLoader({context.pack.process.ocid: context}),
        FakeEmbedder(),
        selector,
        FAKE_THRESHOLDS,
        budget=DailyBudget(budget) if budget is not None else None,
        **kwargs,
    )


def fact_ids(context: ProcessContext) -> list[str]:
    return [f.fact_id for f in context.facts]


__all__ = ["QaFact", "fact_ids", "make_context", "make_service"]


class LogCapture:
    """Every record of the whole `veedor` logger tree, whatever other tests did to propagation or levels."""

    def __init__(self) -> None:
        import logging

        self.records: list[logging.LogRecord] = []
        self._loggers = [logging.getLogger("veedor.ask")]
        outer = self

        class Handler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                outer.records.append(record)

        self._handler = Handler(level=logging.DEBUG)
        self._saved: list[tuple[object, int, bool]] = []

    def __enter__(self) -> LogCapture:
        for logger in self._loggers:
            self._saved.append((logger, logger.level, logger.disabled))
            logger.setLevel(1)
            logger.disabled = False
            logger.addHandler(self._handler)
        return self

    def __exit__(self, *exc: object) -> None:
        for logger, level, disabled in self._saved:
            logger.removeHandler(self._handler)
            logger.setLevel(level)
            logger.disabled = disabled

    @property
    def text(self) -> str:
        return "\n".join(f"{r.getMessage()} {r.name}" for r in self.records)
