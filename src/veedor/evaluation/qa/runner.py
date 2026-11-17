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
from veedor.domain.qa import ranking
from veedor.domain.qa.screen import Intent, classify_question, validate_question
from veedor.domain.qa.selection import DEFAULT_THRESHOLDS, Thresholds, retrieval_select, top_indices
from veedor.evaluation.qa.generate import (
    ADVERSARIAL,
    ANSWERABLE,
    UNANSWERABLE,
    EvalQuestion,
    ProcessView,
    development_set,
    dropped_duplicates,
    generate,
    generate_phrasing_set,
    heldout2_set,
    heldout_adversarial_set,
    probe_set,
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


def tune_legacy(service: AskService, contexts: dict[str, ProcessContext], questions: list[EvalQuestion]) -> dict[str, Any]:
    """The earlier retrieval (key phrases): floor and k on the tuning half, maximising the mean of the answerable F1
    and the abstention rate. Kept only to measure the new retrieval against it."""
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


# The intent retrieval has more numbers than a floor and a k. They are chosen by coordinate descent on the tuning
# half of the processes, with the original AND the development phrasings of those processes (the held-out phrasings
# are never used), maximising the mean over both sets of (answerable F1 + abstention) / 2.
INTENT_GRID: dict[str, list[float | int]] = {
    "floor": [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5],
    "lexical_weight": [0.3, 0.4, 0.5, 0.6, 0.7],
    "e_lo": [0.2, 0.3, 0.4, 0.5],
    "e_hi": [0.8, 0.9, 0.95, 1.0],
    "oos_margin": [-0.1, -0.05, 0.0, 0.05, 0.1],
    "absent_margin": [-0.15, -0.1, -0.05, 0.0, 0.05, 0.1],
    "second_gap": [0.0, 0.03, 0.05, 0.1],
    "foreign_oos": [0.0, 0.5, 0.9, 1.2, 1.5],
    "foreign_penalty": [0.0, 0.25, 0.5, 0.75, 1.0],
    "k": [1, 2],
}
TUNING_ROUNDS = 3


def _objective(rows: list[tuple[EvalQuestion, ranking.IntentScores | None, list[str], dict[str, tuple[int, ...]]]], t: Thresholds) -> tuple[float, float, float, float]:
    """``(objective, recall, precision, abstention)`` of one set of questions under `t`."""
    recalls, precisions, abstained = [], [], []
    for item, scores, ids, mapping in rows:
        chosen = [] if scores is None else [ids[i] for i in ranking.decide(scores, mapping, t).chosen]
        if item.kind == ANSWERABLE:
            hit = len(set(chosen) & set(item.expected))
            recalls.append(hit / len(item.expected))
            precisions.append(hit / len(chosen) if chosen else 0.0)
        else:
            abstained.append(0.0 if chosen else 1.0)
    recall, precision, abstention = float(np.mean(recalls)), float(np.mean(precisions)), float(np.mean(abstained))
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
    return (f1 + abstention) / 2, recall, precision, abstention


def tune_intents(service: AskService, contexts: dict[str, ProcessContext], phrasing_sets: dict[str, list[EvalQuestion]]) -> dict[str, Any]:
    """Coordinate descent over `INTENT_GRID`, on the answerable and unanswerable questions of each given set."""
    ids = {ocid: [f.fact_id for f in ctx.facts] for ocid, ctx in contexts.items()}
    mappings = {ocid: ranking.facts_by_intent(i) for ocid, i in ids.items()}
    prepared: dict[str, list] = {}
    for name, questions in phrasing_sets.items():
        items = [q for q in questions if q.kind in (ANSWERABLE, UNANSWERABLE)]
        scores = _intent_rows(service, contexts, items)
        prepared[name] = [(item, score, ids[item.ocid], mappings[item.ocid]) for item, score in zip(items, scores, strict=True)]

    def total(t: Thresholds) -> float:
        return float(np.mean([_objective(rows, t)[0] for rows in prepared.values()]))

    current = replace(DEFAULT_THRESHOLDS)
    best = total(current)
    for _ in range(TUNING_ROUNDS):
        before = best
        for name, values in INTENT_GRID.items():
            for value in values:
                candidate = replace(current, **{name: value})
                score = total(candidate)
                if score > best + 1e-9:
                    best, current = score, candidate
        if best <= before + 1e-9:
            break
    per_set = {name: dict(zip(("objective", "recall", "precision", "abstention"), (round(v, 4) for v in _objective(rows, current)), strict=True)) for name, rows in prepared.items()}
    # Gate for the model: ask it whenever some expected fact scores above this in 95 % of the answerable questions.
    ceilings = []
    for rows in prepared.values():
        for item, score, fact_ids, _ in rows:
            if item.kind == ANSWERABLE and score is not None:
                fact_scores = ranking.fact_scores(score, fact_ids, current)
                ceilings.append(max(float(fact_scores[fact_ids.index(e)]) for e in item.expected))
    model_floor = float(np.floor(np.percentile(ceilings, 5) / 0.025) * 0.025)
    candidate_recall = float(np.mean([
        all(fact_ids.index(e) in top_indices(ranking.fact_scores(score, fact_ids, current), DEFAULT_THRESHOLDS.candidates) for e in item.expected)
        for rows in prepared.values() for item, score, fact_ids, _ in rows if item.kind == ANSWERABLE and score is not None
    ]))
    chosen = {name: getattr(current, name) for name in INTENT_GRID}
    return {**chosen, "objective": round(best, 4), "model_floor": round(model_floor, 3), "candidate_recall_tuning_half": round(candidate_recall, 4), "per_set": per_set}


def _intent_rows(service: AskService, contexts: dict[str, ProcessContext], questions: list[EvalQuestion]) -> list[ranking.IntentScores | None]:
    out: list[ranking.IntentScores | None] = []
    for item in questions:
        screened = validate_question(item.text)
        if not screened.ok or classify_question(screened.text) is not Intent.ANSWERABLE:
            out.append(None)
        else:
            out.append(service.intent_scores(contexts[item.ocid], screened.text))
    return out


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


def make_service(contexts: dict[str, ProcessContext], embedder: CachedEmbedder, thresholds: Thresholds, selector: ModelSelector | None, retrieval: str = "intents") -> AskService:
    class Fixed:
        def load(self, ocid: str) -> ProcessContext:
            return contexts[ocid]

    return AskService(Fixed(), embedder, selector, thresholds, budget=DailyBudget(10**6) if selector else None, retrieval=retrieval)


HELDOUT_FILES = {
    "heldout": "src/veedor/evaluation/qa/heldout.py",
    "heldout2": "src/veedor/evaluation/qa/heldout2.py",
    "heldout_adversarial": "src/veedor/evaluation/qa/heldout_adversarial.py",
}
HELDOUT_PATH = HELDOUT_FILES["heldout"]
# Sets that are evaluated once (final report) and then only carried over from the previous eval/qa.json.
SINGLE_USE = {"heldout2": heldout2_set, "heldout_adversarial": heldout_adversarial_set}
RESULT_KEY = {"heldout": "retrieval_only_heldout", "heldout2": "retrieval_only_heldout2", "heldout_adversarial": "retrieval_only_heldout_adversarial"}
LEGACY_NOTE = "the earlier retrieval (retrieval keys compared with the question), re-measured in this run on the same questions"
HELDOUT1_SUBSET_NOTE = {
    "subset": "adversarial and judgement questions of the first held-out set",
    "status": "no longer unseen",
    "when": "2026-11-17",
    "why": "its per-question misses (judgement slang such as coima, chanchullo, tongo, negociado, mano negra, coludidos, and hidden-instruction "
    "wordings) were read and the screen was then extended to cover that vocabulary; the answerable and unanswerable subsets of the first held-out set were not read per question",
}


def _file_sha256(relative: str) -> str | None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[4] / relative
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _shipped_thresholds_differ(tuned: dict[str, Any]) -> list[str]:
    """Fields where the thresholds chosen by the tuning differ from the ones the API ships (`DEFAULT_THRESHOLDS`)."""
    return [k for k in (*INTENT_GRID, "model_floor") if getattr(DEFAULT_THRESHOLDS, k) != tuned[k]]


def run_evaluation(settings: Settings, *, with_model: bool, n: int = 600, seed: int = SEED, heldout: bool = False, previous: dict[str, Any] | None = None, progress=print) -> dict[str, Any]:  # noqa: ANN001
    """Original and development phrasings are measured on every run. The held-out sets are not: the first one is
    carried over from the previous `eval/qa.json` (it measured an earlier retrieval and is never re-run); the second
    one and the new adversarial one are evaluated ONCE (`heldout=True`, final report, with exactly the shipped
    thresholds) and carried over afterwards, so `heldout_runs` counts every run that ever happened."""
    started = time.perf_counter()
    previous = previous or {}
    previous_sets: dict[str, Any] = dict(previous.get("heldout_sets") or {})
    if "heldout" not in previous_sets and previous.get("retrieval_only_heldout"):
        previous_sets["heldout"] = {"runs": int(previous.get("heldout_runs", 1)), "retrieval_version": "intents-v1", "evaluated_at": previous.get("generated_at"), "sha256": previous.get("heldout_sha256")}
    to_run = [name for name in SINGLE_USE if heldout and name not in previous_sets]
    if heldout and not to_run:
        raise ValueError("every held-out set was already evaluated once; a held-out set is not run twice")
    ocids = sample_ocids(settings, n, seed)
    progress(f"sampled {len(ocids)} processes; loading their evidence")
    contexts, texts, _ = load_contexts(settings, ocids)
    investigated = set(InvestigationStore(settings.data_dir / "investigations").ocids()) & set(contexts)
    all_views = views_of(contexts, investigated)
    questions = generate(all_views, seed, split_of)
    tune_half = [q for q in questions if split_of(q.ocid) == "tune"]
    report_half = [q for q in questions if split_of(q.ocid) == "report"]
    progress(f"{len(contexts)} processes, {len(questions)} questions ({len(tune_half)} tuning, {len(report_half)} reporting)")
    embedder = CachedEmbedder(lambda: FastEmbedEmbedder(local_files_only=True))
    tune_views = [v for v in all_views if split_of(v.ocid) == "tune"]
    report_views = [v for v in all_views if split_of(v.ocid) == "report"]
    development_tune = generate_phrasing_set(tune_views, development_set(), seed)
    index_started = time.perf_counter()
    ranking.IntentIndex(embedder.embed)  # the one-off cost of the prototype embeddings (the API pays it on the first question)
    index_ms = (time.perf_counter() - index_started) * 1000
    # The developer's own probes (out-of-scope questions sharing a word, competition and comparison wordings) are one more
    # tuning set. Compound questions are scored by the service (clause by clause), not by `decide`: left out here.
    probes_tune = [q for q in generate_phrasing_set(tune_views, probe_set(), seed) if q.tag != "compound"]
    tuning = tune_intents(make_service(contexts, embedder, DEFAULT_THRESHOLDS, None), contexts, {"original": tune_half, "development": development_tune, "probes": probes_tune})
    differ = _shipped_thresholds_differ(tuning)
    if heldout and differ:
        raise ValueError(f"the tuning chose thresholds other than the shipped ones ({differ}): update DEFAULT_THRESHOLDS first; a held-out run needs the final thresholds")
    thresholds = replace(DEFAULT_THRESHOLDS, **{k: tuning[k] for k in (*INTENT_GRID, "model_floor")})
    progress(f"chosen on the tuning half: {({k: tuning[k] for k in INTENT_GRID})}, model floor {thresholds.model_floor}; differs from the shipped thresholds in: {differ or 'nothing'}")
    legacy_tuning = tune_legacy(make_service(contexts, embedder, DEFAULT_THRESHOLDS, None, "legacy"), contexts, tune_half)
    legacy_thresholds = replace(DEFAULT_THRESHOLDS, floor=legacy_tuning["floor"], k=legacy_tuning["k"], model_floor=legacy_tuning["model_floor"])

    development_questions = generate_phrasing_set(report_views, development_set(), seed)
    sets: dict[str, list[EvalQuestion]] = {"original": report_half, "development": development_questions}
    new_service = make_service(contexts, embedder, thresholds, None)
    old_service = make_service(contexts, embedder, legacy_thresholds, None, "legacy")
    summaries = {name: summarise(run_questions(new_service, qs), texts, model=False) for name, qs in sets.items()}
    baseline = {name: summarise(run_questions(old_service, qs), texts, model=False) for name, qs in sets.items()}
    # Held-out sets: run the ones that were never run (once), carry the others over unchanged.
    now = datetime.now(UTC).isoformat(timespec="seconds")
    held: dict[str, dict[str, Any] | None] = {}
    held_meta: dict[str, dict[str, Any]] = {}
    for name in HELDOUT_FILES:
        key = RESULT_KEY[name]
        if name in to_run:
            qs = generate_phrasing_set(report_views, SINGLE_USE[name](), seed)
            held[name] = summarise(run_questions(new_service, qs), texts, model=False)
            held_meta[name] = {"runs": 1, "retrieval_version": ranking.RETRIEVAL_VERSION, "evaluated_at": now, "sha256": _file_sha256(HELDOUT_FILES[name]), "questions": len(qs), "kinds": dict(Counter(q.kind for q in qs)), "status": "evaluated in this run"}
        else:
            held[name] = previous.get(key)
            old = dict(previous_sets.get(name) or {})
            if name == "heldout":
                old.setdefault("retrieval_version", "intents-v1")
                old["status"] = "carried over, not re-run: measured the earlier retrieval (" + str(old["retrieval_version"]) + ")"
                old["questions"] = previous.get("sample", {}).get("questions_by_phrasing_set", {}).get("heldout", {}).get("total")
                old["sha256"] = old.get("sha256") or previous.get("heldout_sha256")
                old["adversarial_subset_unseen"] = HELDOUT1_SUBSET_NOTE
            elif old:
                old["status"] = "carried over, not re-run"
            if old:
                held_meta[name] = old
    carried_runs = sum(int(m.get("runs", 0)) for k, m in held_meta.items() if k not in to_run)
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
            "questions_by_phrasing_set": {name: {"total": len(qs), "by_kind": dict(Counter(q.kind for q in qs))} for name, qs in sets.items()}
            | {name: {"total": m["questions"], "by_kind": m.get("kinds") or (previous.get("sample", {}).get("questions_by_phrasing_set", {}).get(name, {}).get("by_kind"))} for name, m in held_meta.items() if m.get("questions")},
            "questions_tuning_development_phrasing": len(development_tune),
        },
        "thresholds": {k: tuning[k] for k in (*INTENT_GRID, "objective", "model_floor", "candidate_recall_tuning_half", "per_set")}
        | {"candidates": thresholds.candidates, "quote_floor": thresholds.quote_floor, "max_quotes": thresholds.max_quotes},
        "legacy_thresholds": {k: legacy_tuning[k] for k in ("floor", "k", "model_floor", "objective")},
        "phrasing_sets": {
            "original": "training and tuning phrasings (written together with the retrieval keys)",
            "development": "independently worded set of review 5, now seen by the developers and tuned against",
            "heldout": "written before any tuning of the first intent retrieval (intents-v1); not used for tuning; evaluated once, with intents-v1; its adversarial subset is no longer unseen",
            "heldout2": "written before the tuning of intents-v2; not used for tuning; evaluated once",
            "heldout_adversarial": "new adversarial and judgement set, written before the screen was extended; not used to choose any pattern; evaluated once",
        },
        "retrieval_version": ranking.RETRIEVAL_VERSION,
        # What the previous retrieval (intents-v1) measured on the original and development phrasings, kept for the
        # before/after table; carried over from the first file that has it.
        "retrieval_v1": previous.get("retrieval_v1")
        or (
            {"measured_at": previous.get("generated_at"), "thresholds": previous.get("thresholds"), "original": previous["retrieval_only"], "development": previous.get("retrieval_only_development")}
            if previous.get("retrieval_only") and previous.get("retrieval_version") in (None, "intents-v1")
            else None
        ),
        "probe_questions_tuned_on": {"out_of_scope_shared_word": len(probe_set().off_topic), "competition": len(probe_set().answerable["tenderers"]), "comparison": len(probe_set().comparison)},
        "dropped_duplicates": dropped_duplicates(),
        "heldout_sets": held_meta,
        "heldout_sha256": _file_sha256(HELDOUT_PATH),
        "heldout_evaluated": bool(held_meta.get("heldout")),
        "heldout_runs": carried_runs + len(to_run),  # every run of every held-out set, ever
        "intent_index_build_ms": round(index_ms, 1),
        "retrieval_only": summaries["original"],  # original phrasings, reporting-half processes
        "retrieval_only_development": summaries["development"],
        "retrieval_only_heldout": held["heldout"],  # the FIRST held-out set, measured with intents-v1 (carried over)
        "retrieval_only_heldout2": held["heldout2"],
        "retrieval_only_heldout_adversarial": held["heldout_adversarial"],
        "baseline_legacy": {"note": LEGACY_NOTE, "original": baseline["original"], "development": baseline["development"], "heldout": (previous.get("baseline_legacy") or {}).get("heldout")},
        "tuning_grid": legacy_tuning["grid"],
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
                "measured_on": "in_vocabulary_phrasings",  # not rerun on the other sets (cost)
                "model": model.model_name,
                "questions": len(sub),
                "model_mode": summarise(model_outcomes, texts, model=True),
                "retrieval_same_questions": summarise(run_questions(make_service(contexts, embedder, thresholds, None), sub), texts, model=False),
            }
    result["wall_seconds"] = round(time.perf_counter() - started, 1)
    return result
