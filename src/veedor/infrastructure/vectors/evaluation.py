"""Retrieval-quality measurement with CPC codes as a proxy label (numbers only, no identifiers).

The proxy: a neighbour counts as agreeing when it shares the query's CPC 5-digit prefix. It is NOT
relevance: two processes can differ in CPC and still be the same kind of purchase, and the embedded text
contains the CPC description, which makes the full-index number optimistic. The pool experiment embeds the
description alone (no CPC text) for the same processes to quantify that leakage.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from veedor.infrastructure.vectors.embedding import EmbeddingPort
from veedor.infrastructure.vectors.repository import PgVectorStore
from veedor.infrastructure.vectors.source import LakeProcessSource
from veedor.use_cases.build_vectors import STATUS_FULL, compose_text, content_hash, prepare
from veedor.use_cases.similar_processes import find_similar

K = 10
PREFIX = 5
N_BOOT = 2_000
SEED = 42
DOC_BEGIN = "<!-- BEGIN GENERATED: evaluation -->"
DOC_END = "<!-- END GENERATED: evaluation -->"


@dataclass(frozen=True, slots=True)
class Interval:
    mean: float
    low: float
    high: float

    def as_dict(self) -> dict[str, float]:
        return {"mean": round(self.mean, 4), "ci95_low": round(self.low, 4), "ci95_high": round(self.high, 4)}


def bootstrap(values: np.ndarray, *, seed: int = SEED, n_boot: int = N_BOOT) -> Interval:
    """Mean with a percentile bootstrap 95 % interval over per-query values (fixed seed)."""
    if len(values) == 0:
        return Interval(float("nan"), float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = rng.choice(values, size=(n_boot, len(values)), replace=True).mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return Interval(float(values.mean()), float(low), float(high))


def prefix_code(cpc: str | None, n: int | None) -> str:
    return "" if not cpc else (cpc if n is None else cpc[:n])


def agreement(query_code: str, neighbour_codes: Sequence[str]) -> float:
    """Share of the returned neighbours whose code equals the query's (empty codes never agree)."""
    if not neighbour_codes or not query_code:
        return 0.0
    return sum(1 for code in neighbour_codes if code and code == query_code) / len(neighbour_codes)


# ------------------------------------------------------------------------- full index (pgvector)


def _full_index(store: PgVectorStore, queries: int, seed: int) -> tuple[dict, list[str]]:
    ocids, cpcs = store.metadata_arrays()
    c5 = [prefix_code(c, PREFIX) for c in cpcs]
    c9 = [prefix_code(c, None) for c in cpcs]
    position = {o: i for i, o in enumerate(ocids)}
    rng = np.random.default_rng(seed)
    eligible = np.array([i for i, c in enumerate(c5) if len(c) == PREFIX])
    chosen = rng.choice(eligible, size=min(queries, len(eligible)), replace=False)
    by_exact: dict[str, list[int]] = {}
    for i, code in enumerate(c9):
        if code:
            by_exact.setdefault(code, []).append(i)

    emb, emb9, rnd, exact, exact_pool = [], [], [], [], []
    short_exact = 0
    for q in chosen:
        found = [position[n.ocid] for n in store.neighbours(ocids[q], K, False) if n.ocid in position]
        emb.append(agreement(c5[q], [c5[i] for i in found]))
        emb9.append(agreement(c9[q], [c9[i] for i in found]))
        draw = [i for i in rng.choice(len(ocids), size=K + 1, replace=False) if i != q][:K]
        rnd.append(agreement(c5[q], [c5[i] for i in draw]))
        candidates = [i for i in by_exact.get(c9[q], ()) if i != q]
        exact_pool.append(len(candidates))
        short_exact += len(candidates) < K
        picks = (
            list(rng.choice(candidates, size=min(K, len(candidates)), replace=False)) if candidates else []
        )
        exact.append(agreement(c5[q], [c5[i] for i in picks]) if picks else float("nan"))
    exact_arr = np.array(exact)
    with_exact = exact_arr[~np.isnan(exact_arr)]
    result = {
        "indexed_rows": len(ocids),
        "indexed_rows_with_cpc": int(sum(1 for c in c5 if len(c) == PREFIX)),
        "queries": int(len(chosen)),
        "k": K,
        "agreement_at_10_cpc5": {
            "embedding": bootstrap(np.array(emb)).as_dict(),
            "random_neighbour_baseline": bootstrap(np.array(rnd), seed=seed + 1).as_dict(),
            "exact_cpc_baseline": bootstrap(with_exact, seed=seed + 2).as_dict(),
        },
        "exact_cpc_baseline_note": (
            "Neighbours drawn at random among processes with the identical 9-digit CPC; they share the "
            "5-digit prefix by construction, so this baseline is a ceiling of 1.0, not a competitor."
        ),
        "exact_cpc_baseline_queries_with_a_candidate": int(len(with_exact)),
        "exact_cpc_baseline_queries_with_fewer_than_10_candidates": int(short_exact),
        "embedding_neighbours_sharing_exact_cpc9": bootstrap(np.array(emb9), seed=seed + 3).as_dict(),
    }
    return result, [ocids[q] for q in chosen]


# ----------------------------------------------------------------- pool experiment (leakage)


def _top_k(similarity: np.ndarray, k: int) -> np.ndarray:
    part = np.argpartition(-similarity, k, axis=1)[:, :k]
    order = np.argsort(-np.take_along_axis(similarity, part, axis=1), axis=1)
    return np.take_along_axis(part, order, axis=1)


def _pool_agreement(
    queries: np.ndarray, vectors: np.ndarray, c5: list[str], text_ids: list[str], *, dedup: bool
) -> np.ndarray:
    sim = vectors[queries] @ vectors.T
    sim[np.arange(len(queries)), queries] = -np.inf
    if dedup:  # drop neighbours whose description text is identical to the query's
        ids = np.array(text_ids)
        sim[ids[queries][:, None] == ids[None, :]] = -np.inf
    top = _top_k(sim, K)
    return np.array([agreement(c5[q], [c5[i] for i in row]) for q, row in zip(queries, top, strict=True)])


def _pool_baselines(queries: np.ndarray, c5: list[str], seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    by_code: dict[str, list[int]] = {}
    for i, code in enumerate(c5):
        by_code.setdefault(code, []).append(i)
    rnd, exact = [], []
    for q in queries:
        draw = [i for i in rng.choice(len(c5), size=K + 1, replace=False) if i != q][:K]
        rnd.append(agreement(c5[q], [c5[i] for i in draw]))
        same = [i for i in by_code[c5[q]] if i != q]
        picks = list(rng.choice(same, size=min(K, len(same)), replace=False)) if same else []
        exact.append(agreement(c5[q], [c5[i] for i in picks]) if picks else float("nan"))
    return np.array(rnd), np.array(exact)


def _pool(
    store: PgVectorStore, source: LakeProcessSource, embedder: EmbeddingPort, pool_size: int, queries: int,
    seed: int,
) -> dict:  # fmt: skip
    ocids, cpcs = store.metadata_arrays()
    rng = np.random.default_rng(seed + 10)
    eligible = [o for o, c in zip(ocids, cpcs, strict=True) if c and len(c) >= PREFIX]
    candidates = [eligible[i] for i in rng.permutation(len(eligible))[: pool_size * 2]]
    kept = []
    for record in source.records(None, candidates):
        prepared = prepare(record)
        if prepared is not None and prepared.status == STATUS_FULL and record.main_cpc:
            kept.append(record)
    kept = kept[:pool_size]
    stored = {}
    for start in range(0, len(kept), 5_000):
        stored |= store.vectors_for([r.ocid for r in kept[start : start + 5_000]])
    kept = [r for r in kept if r.ocid in stored]
    with_cpc = np.vstack([stored[r.ocid] for r in kept])
    desc_only = [compose_text(r, include_cpc=False)[0] or "" for r in kept]
    without_cpc = embedder.embed(desc_only)
    c5 = [prefix_code(r.main_cpc, PREFIX) for r in kept]
    text_ids = [content_hash(t) for t in desc_only]
    q = rng.choice(len(kept), size=min(queries, len(kept)), replace=False)
    rnd, exact = _pool_baselines(q, c5, seed + 11)
    out: dict = {"pool_size": len(kept), "queries": int(len(q)), "k": K}
    for dedup in (False, True):
        a = _pool_agreement(q, with_cpc, c5, text_ids, dedup=dedup)
        b = _pool_agreement(q, without_cpc, c5, text_ids, dedup=dedup)
        out["identical_description_neighbours_removed" if dedup else "all_neighbours"] = {
            "with_cpc_text": bootstrap(a).as_dict(),
            "without_cpc_text": bootstrap(b, seed=seed + 4).as_dict(),
            "paired_difference_with_minus_without": bootstrap(a - b, seed=seed + 5).as_dict(),
        }
    out["random_neighbour_baseline"] = bootstrap(rnd, seed=seed + 6).as_dict()
    out["exact_cpc_baseline"] = bootstrap(exact[~np.isnan(exact)], seed=seed + 7).as_dict()
    counts = Counter(text_ids)
    out["queries_with_duplicate_description_in_pool"] = int(sum(1 for i in q if counts[text_ids[i]] > 1))
    return out


# ------------------------------------------------------------------------------------ latency


def _latency(ocids: Sequence[str], n: int, store: PgVectorStore) -> dict:
    sample = list(ocids)[:n]
    find_similar(sample[0], 10, store=store)  # warm-up: connection, lake views, buyer-name cache
    times = []
    for ocid in sample:
        t0 = time.perf_counter()
        find_similar(ocid, 10, store=store)
        times.append((time.perf_counter() - t0) * 1000)
    arr = np.array(times)
    return {
        "queries": len(sample),
        "k": 10,
        "p50_ms": round(float(np.percentile(arr, 50)), 1),
        "p95_ms": round(float(np.percentile(arr, 95)), 1),
        "max_ms": round(float(arr.max()), 1),
        "includes": "index lookup, ANN search and buyer-name lookup in the lake (buyer cache warms up)",
    }


# ---------------------------------------------------------------------------------- orchestration


def run_evaluation(
    store: PgVectorStore, source: LakeProcessSource, embedder: EmbeddingPort, *, sample: int = 1_000,
    pool_size: int = 20_000, latency_queries: int = 200, seed: int = SEED,
) -> dict:  # fmt: skip
    status = store.status()
    full, query_ocids = _full_index(store, sample, seed)
    return {
        "generated_on": date.today().isoformat(),
        "model": embedder.model_name,
        "dimension": embedder.dimension,
        "seed": seed,
        "bootstrap_resamples": N_BOOT,
        "index": {"rows": status.rows, "models": status.models, "definition": status.index_definition},
        "full_index": full,
        "pool_experiment": _pool(store, source, embedder, pool_size, sample, seed),
        "latency": _latency(query_ocids, latency_queries, store),
        "caveats": [
            "CPC agreement is a proxy, not relevance: similar purchases can carry different CPC codes.",
            "The embedded text includes the CPC description, so the full-index number is optimistic.",
            "The pool experiment embeds the description without the CPC text to measure that leakage.",
            "Identical descriptions (re-tendered objects) inflate agreement; the pool experiment also "
            "reports the result with identical-description neighbours removed.",
        ],
    }


def _pct(interval: dict) -> str:
    mean, low, high = (interval[key] * 100 for key in ("mean", "ci95_low", "ci95_high"))
    return f"{mean:.1f} % [{low:.1f}, {high:.1f}]"


def render_markdown(result: dict) -> str:
    """The generated documentation section: every number comes from the JSON."""
    f, p, lat = result["full_index"], result["pool_experiment"], result["latency"]
    a = f["agreement_at_10_cpc5"]
    allp, dd = p["all_neighbours"], p["identical_description_neighbours_removed"]
    return "\n".join(
        [
            DOC_BEGIN,
            f"Generated by `veedor vectors evaluate` on {result['generated_on']} (seed {result['seed']}, "
            f"{result['bootstrap_resamples']} bootstrap resamples; values are mean [95 % interval]).",
            "",
            f"Index: {result['index']['rows']:,} rows, model `{result['model']}` "
            f"({result['dimension']} dimensions).",
            "",
            f"**Full index** ({f['queries']:,} random query processes, top-{f['k']} from pgvector):",
            "",
            "| Measure | Value |",
            "|---|---|",
            f"| CPC 5-digit agreement@10, embedding neighbours | {_pct(a['embedding'])} |",
            f"| Same, random-neighbour baseline | {_pct(a['random_neighbour_baseline'])} |",
            f"| Same, exact-CPC baseline (ceiling by construction) | {_pct(a['exact_cpc_baseline'])} |",
            "| Embedding neighbours with the identical 9-digit CPC | "
            f"{_pct(f['embedding_neighbours_sharing_exact_cpc9'])} |",
            f"| Queries with fewer than 10 other processes of the same 9-digit CPC | "
            f"{f['exact_cpc_baseline_queries_with_fewer_than_10_candidates']:,} of {f['queries']:,} |",
            "",
            f"**CPC-text leakage** (pool of {p['pool_size']:,} processes with a safe description, "
            f"{p['queries']:,} queries, exact search inside the pool):",
            "",
            "| Variant | Embedding includes CPC text | Description only |",
            "|---|---|---|",
            f"| All neighbours | {_pct(allp['with_cpc_text'])} | {_pct(allp['without_cpc_text'])} |",
            f"| Identical-description neighbours removed | {_pct(dd['with_cpc_text'])} | "
            f"{_pct(dd['without_cpc_text'])} |",
            "",
            f"Pool baselines: random neighbours {_pct(p['random_neighbour_baseline'])}; "
            f"exact-CPC {_pct(p['exact_cpc_baseline'])}.",
            "",
            f"**Latency** of `find_similar` over {lat['queries']} queries: p50 {lat['p50_ms']} ms, "
            f"p95 {lat['p95_ms']} ms, max {lat['max_ms']} ms.",
            DOC_END,
        ]
    )


def update_docs(doc_path: Path, markdown: str) -> bool:
    """Replace the generated block in the docs file; returns False when the markers are absent."""
    if not doc_path.is_file():
        return False
    text = doc_path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(DOC_BEGIN) + r".*?" + re.escape(DOC_END), re.DOTALL)
    if not pattern.search(text):
        return False
    doc_path.write_text(pattern.sub(lambda _: markdown, text), encoding="utf-8")
    return True
