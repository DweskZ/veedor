# ruff: noqa: E501
"""Run the evaluation: sample processes, generate the sets, tune on one half, report on the other."""

from __future__ import annotations

import hashlib
import itertools
import random
import time
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import duckdb
import numpy as np

from veedor.agents.qa.selector import ModelSelector
from veedor.core.settings import Settings
from veedor.domain.qa.screen import Intent, classify_question, validate_question
from veedor.domain.qa.selection import DEFAULT_THRESHOLDS, Thresholds, retrieval_select, top_indices
from veedor.evaluation.qa.generate import (
    ADVERSARIAL,
    ANSWERABLE,
    UNANSWERABLE,
    EvalQuestion,
    ProcessView,
    generate,
    view_of,
)
from veedor.evaluation.qa.metrics import Outcome, ProcessText, summarise
from veedor.infrastructure.investigations.store import InvestigationStore
from veedor.infrastructure.lake.evidence_reader import EvidenceReader
from veedor.infrastructure.lake.reader import LakeReader
from veedor.infrastructure.llm.structured import build_structured_model
from veedor.infrastructure.qa.embedding_cache import CachedEmbedder
from veedor.infrastructure.vectors.embedding import FastEmbedEmbedder
from veedor.use_cases.ask import AskService, DailyBudget, InvalidQuestionError, ProcessContext
from veedor.use_cases.queries.ask_context import ApiContextLoader
from veedor.use_cases.queries.processes import name_context

SEED = 42
FLOORS = [round(0.25 + 0.025 * i, 3) for i in range(0, 19)]  # 0.25 .. 0.70
KS = (1, 2, 3, 4)
MODEL_ANSWERABLE, MODEL_UNANSWERABLE = 60, 40


def split_of(ocid: str) -> str:
    """Stable half of a process: ``tune`` or ``report``. Questions of one process never straddle the halves."""
    return "tune" if int(hashlib.sha256(f"split:{ocid}".encode()).hexdigest()[:8], 16) % 2 == 0 else "report"


def sample_ocids(settings: Settings, n: int, seed: int = SEED) -> list[str]:
    """A seeded sample: two thirds with a risk signal, one third without, plus every stored investigation."""
    con = duckdb.connect()
    scores = str(settings.marts_dir / "process_scores.parquet").replace("'", "''")
    flagged = n * 2 // 3
    rows = con.execute(
        f"SELECT ocid FROM (SELECT ocid, n_signals FROM read_parquet('{scores}')) "
        f"WHERE n_signals >= 1 ORDER BY hash(ocid || '{seed}') LIMIT {flagged}"
    ).fetchall()
    rows += con.execute(
        f"SELECT ocid FROM read_parquet('{scores}') WHERE n_signals = 0 "
        f"ORDER BY hash(ocid || '{seed}') LIMIT {n - flagged}"
    ).fetchall()
    chosen = {r[0] for r in rows}
    chosen.update(InvestigationStore(settings.data_dir / "investigations").ocids())
    return sorted(chosen)


def load_contexts(settings: Settings, ocids: list[str]) -> tuple[dict[str, ProcessContext], dict[str, ProcessText], LakeReader]:
    lake = LakeReader(settings.lake_dir, settings.marts_dir)
    reader = EvidenceReader(settings.lake_dir, settings.marts_dir)
    store = InvestigationStore(settings.data_dir / "investigations")

    def stored(ocid: str):  # noqa: ANN202
        record = store.load(ocid)
        return record.facts if record is not None and record.withheld is None else None

    loader = ApiContextLoader(lake, reader.load, stored)
    contexts: dict[str, ProcessContext] = {}
    texts: dict[str, ProcessText] = {}
    for ocid in ocids:
        try:
            context = loader.load(ocid)
        except Exception:  # noqa: BLE001 - a process the pack cannot be built for is skipped, counted by size
            continue
        contexts[ocid] = context
        persons, protected = name_context(lake, ocid)
        texts[ocid] = ProcessText(
            fact_text={f.fact_id: f.text for f in context.facts},
            quote_text=frozenset(p.text for item in context.quotes for p in item.passages),
            persons=tuple(persons),
            protected=tuple(protected),
        )
    return contexts, texts, lake


def views_of(contexts: dict[str, ProcessContext], investigated: set[str]) -> list[ProcessView]:
    from veedor.domain.signals import SIGNALS_BY_CODE

    out = []
    for ocid, ctx in contexts.items():
        labels = {
            f.fact_id: SIGNALS_BY_CODE[f.fact_id.split(":", 1)[1]].label_es
            for f in ctx.facts
            if f.fact_id.startswith("signal:") and f.fact_id.split(":", 1)[1] in SIGNALS_BY_CODE
        }
        winner = ctx.pack.winner
        company = bool(winner and winner.kind in ("company", "public_entity") and winner.ruc)
        out.append(view_of(ocid, ctx.facts, labels, company, ocid in investigated))
    return out


# --- tuning ------------------------------------------------------------------------------------------------


def _scores(service: AskService, contexts: dict[str, ProcessContext], questions: list[EvalQuestion]) -> list[np.ndarray | None]:
    """Similarity of every answerable or unanswerable question to the facts of its process (None: the
    screen answers it with a fixed sentence whatever the thresholds are)."""
    out: list[np.ndarray | None] = []
    for item in questions:
        screened = validate_question(item.text)
        if not screened.ok or classify_question(screened.text) is not Intent.ANSWERABLE:
            out.append(None)
        else:
            out.append(service.score_facts(contexts[item.ocid], screened.text))
    return out


def tune(service: AskService, contexts: dict[str, ProcessContext], questions: list[EvalQuestion]) -> dict[str, Any]:
    """Choose floor and k on the tuning half: maximise the mean of the answerable F1 and the abstention rate."""
    items = [q for q in questions if q.kind in (ANSWERABLE, UNANSWERABLE)]
    scores = _scores(service, contexts, items)
    ids = {ocid: [f.fact_id for f in ctx.facts] for ocid, ctx in contexts.items()}
    best, grid = None, []
    for floor, k in itertools.product(FLOORS, KS):
        t = replace(DEFAULT_THRESHOLDS, floor=floor, k=k)
        recalls, precisions, abstained = [], [], []
        for item, score in zip(items, scores, strict=True):
            chosen = [] if score is None else [ids[item.ocid][i] for i in retrieval_select(score, t)]
            if item.kind == ANSWERABLE:
                hit = len(set(chosen) & set(item.expected))
                recalls.append(hit / len(item.expected))
                precisions.append(hit / len(chosen) if chosen else 0.0)
            else:
                abstained.append(0.0 if chosen else 1.0)
        recall, precision = float(np.mean(recalls)), float(np.mean(precisions))
        f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
        objective = (f1 + float(np.mean(abstained))) / 2
        grid.append({"floor": floor, "k": k, "recall": round(recall, 4), "precision": round(precision, 4), "abstention": round(float(np.mean(abstained)), 4), "objective": round(objective, 4)})
        if best is None or objective > best[0]:
            best = (objective, floor, k)
    assert best is not None
    # Gate for the model: ask it whenever some expected fact is above this similarity in 95 % of the
    # answerable questions of the tuning half.
    ceiling = [
        max(float(score[ids[item.ocid].index(e)]) for e in item.expected)
        for item, score in zip(items, scores, strict=True)
        if item.kind == ANSWERABLE and score is not None
    ]
    model_floor = float(np.floor(np.percentile(ceiling, 5) / 0.025) * 0.025)
    candidate_recall = float(np.mean([
        all(ids[item.ocid].index(e) in top_indices(score, DEFAULT_THRESHOLDS.candidates) for e in item.expected)
        for item, score in zip(items, scores, strict=True)
        if item.kind == ANSWERABLE and score is not None
    ]))
    return {"floor": best[1], "k": best[2], "objective": round(best[0], 4), "model_floor": round(model_floor, 3),
            "candidate_recall_tuning_half": round(candidate_recall, 4), "grid": grid}


# --- running ----------------------------------------------------------------------------------------------


def run_questions(service: AskService, questions: list[EvalQuestion]) -> list[Outcome]:
    out: list[Outcome] = []
    for item in questions:
        started = time.perf_counter()
        try:
            answer = service.ask(item.ocid, item.text)
            rejected = None
        except InvalidQuestionError as exc:
            answer, rejected = None, exc.problem.value
        out.append(Outcome(item, answer, (time.perf_counter() - started) * 1000, rejected))
    return out


def model_subsample(questions: list[EvalQuestion], seed: int = SEED) -> list[EvalQuestion]:
    """About 150 questions for the model run: answerable, unanswerable and each attack once."""
    rng = random.Random(seed)
    answerable = [q for q in questions if q.kind == ANSWERABLE]
    unanswerable = [q for q in questions if q.kind == UNANSWERABLE]
    seen: set[int] = set()
    attacks = []
    for q in questions:
        if q.kind == ADVERSARIAL and q.attack not in seen:
            seen.add(q.attack)  # type: ignore[arg-type]
            attacks.append(q)
    return [*rng.sample(answerable, min(MODEL_ANSWERABLE, len(answerable))), *rng.sample(unanswerable, min(MODEL_UNANSWERABLE, len(unanswerable))), *attacks]


def make_service(contexts: dict[str, ProcessContext], embedder: CachedEmbedder, thresholds: Thresholds, selector: ModelSelector | None) -> AskService:
    class Fixed:
        def load(self, ocid: str) -> ProcessContext:
            return contexts[ocid]

    return AskService(Fixed(), embedder, selector, thresholds, budget=DailyBudget(10**6) if selector else None)


def run_evaluation(settings: Settings, *, with_model: bool, n: int = 600, seed: int = SEED, progress=print) -> dict[str, Any]:  # noqa: ANN001
    started = time.perf_counter()
    ocids = sample_ocids(settings, n, seed)
    progress(f"sampled {len(ocids)} processes; loading their evidence")
    contexts, texts, _ = load_contexts(settings, ocids)
    investigated = set(InvestigationStore(settings.data_dir / "investigations").ocids()) & set(contexts)
    questions = generate(views_of(contexts, investigated), seed, split_of)
    tune_half = [q for q in questions if split_of(q.ocid) == "tune"]
    report_half = [q for q in questions if split_of(q.ocid) == "report"]
    progress(f"{len(contexts)} processes, {len(questions)} questions ({len(tune_half)} tuning, {len(report_half)} reporting)")
    embedder = CachedEmbedder(lambda: FastEmbedEmbedder(local_files_only=True))
    tuning = tune(make_service(contexts, embedder, DEFAULT_THRESHOLDS, None), contexts, tune_half)
    thresholds = replace(DEFAULT_THRESHOLDS, floor=tuning["floor"], k=tuning["k"], model_floor=tuning["model_floor"])
    progress(f"chosen on the tuning half: floor {thresholds.floor}, k {thresholds.k}, model floor {thresholds.model_floor}")
    retrieval = summarise(run_questions(make_service(contexts, embedder, thresholds, None), report_half), texts, model=False)
    result: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": seed,
        "sample": {
            "processes": len(contexts),
            "processes_tuning_half": len({q.ocid for q in tune_half}),
            "processes_reporting_half": len({q.ocid for q in report_half}),
            "with_stored_investigation": len(investigated),
            "questions_total": len(questions),
            "questions_by_kind": dict(Counter(q.kind for q in questions)),
            "questions_tuning_half": len(tune_half),
            "questions_reporting_half": len(report_half),
            "distinct_attacks": len({q.attack for q in questions if q.kind == ADVERSARIAL}),
        },
        "thresholds": {k: tuning[k] for k in ("floor", "k", "model_floor", "objective", "candidate_recall_tuning_half")}
        | {"candidates": thresholds.candidates, "quote_floor": thresholds.quote_floor, "max_quotes": thresholds.max_quotes},
        "tuning_grid": tuning["grid"],
        "retrieval_only": retrieval,
        "model": None,
    }
    if with_model:
        model = build_structured_model(settings)
        if model is None:
            result["model"] = {"status": "not_configured"}
        else:
            sub = model_subsample(report_half, seed)
            progress(f"model mode over {len(sub)} questions with {model.model_name}")
            model_outcomes = run_questions(make_service(contexts, embedder, thresholds, ModelSelector(model)), sub)
            result["model"] = {
                "status": "ran",
                "model": model.model_name,
                "questions": len(sub),
                "model_mode": summarise(model_outcomes, texts, model=True),
                "retrieval_same_questions": summarise(run_questions(make_service(contexts, embedder, thresholds, None), sub), texts, model=False),
            }
    result["wall_seconds"] = round(time.perf_counter() - started, 1)
    return result
