"""Measurements of the quotes mart, from the real data (no labels needed).

* coverage of flagged processes by signal and the exclusions by reason (from the build summary);
* the calibration of the similarity floor on a calibration sample, and the label-free retrieval check on
  the *other* processes: how often the selected quote contains a deadline stem (SHORT_TENDER_WINDOW) or a
  price stem (LOW_SAVING), against a random eligible item of the same process, with bootstrap intervals;
* a privacy sweep over every stored quote: the identifier scan, a name search that is independent of the
  masking code (consecutive name tokens, either order), and plain phone and e-mail patterns;
* a random sample of quotes for manual reading.

Only numbers go to ``eval/quotes.json``; the sample is returned separately for the reader to classify.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import orjson

from veedor.core.settings import Settings
from veedor.domain.dossier.text import norm
from veedor.domain.investigation.identifiers import document_has_personal_identifier
from veedor.domain.quotes.gate import ALL_RULES, REVIEWER_RULES, rules_hit
from veedor.domain.quotes.lexicon import Lexicon
from veedor.domain.quotes.names import probable_person_name
from veedor.domain.quotes.screen import check_passage
from veedor.domain.quotes.strict import blank_protected
from veedor.infrastructure.lake.connection import parquet_path, quote_literal
from veedor.infrastructure.quotes.source import LakeQuoteSource
from veedor.infrastructure.vectors.embedding import FastEmbedEmbedder
from veedor.use_cases import build_quotes as bq

SEED = 42
BOOTSTRAP = 2_000
CALIBRATION_PROCESSES = 6_000
FLOOR_GRID = tuple(round(x, 2) for x in np.arange(0.10, 0.55, 0.05))
STEMS = {
    "SHORT_TENDER_WINDOW": re.compile(r"\b(?:plazo|prorrog|dias|fecha|ampli)"),
    "LOW_SAVING": re.compile(
        r"\b(?:precio|presupuesto|valor|monto|descuento|costo|puja|rebaja|oferta economica)"
    ),
}
_STOPWORDS = frozenset({"de", "del", "la", "las", "los", "y", "e"})
_WORDS = re.compile(r"[a-z0-9]+")
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_PHONE = re.compile(r"(?<![\w-])(?:\+?593|0)[\s.\-]?[2-9](?:[\s.\-]?[0-9]){7,8}(?![\w-])")
_SENOR_NAME = re.compile(
    r"\bSe[ñn]or(?:a|ita)?\.?\s+(?!(?:Oferente|Proveedor|Presidente|Presidenta|Gerente|Alcalde|Alcaldesa|Delegad|Director)\w*)"
    r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+"
)
_PHONE_CUE = re.compile(r"\b(?:tel|telf|telefono|celular|whatsapp|fono)\b\D{0,12}[0-9]{6,}")


def _tokens(text: str) -> list[str]:
    return _WORDS.findall(norm(text))


def _name_pairs(name: str) -> set[tuple[str, str]]:
    words = [w for w in _tokens(name) if w not in _STOPWORDS and len(w) >= 2]
    return {(a, b) for a, b in zip(words, words[1:], strict=False)}


def _contains_name(words: list[str], pairs: set[tuple[str, str]]) -> bool:
    if not pairs:
        return False
    both = pairs | {(b, a) for a, b in pairs}
    return any((a, b) in both for a, b in zip(words, words[1:], strict=False))


# ------------------------------------------------------------------------------------ statistics


def bootstrap_ci(values: np.ndarray, rng: np.random.Generator, resamples: int = BOOTSTRAP) -> list[float]:
    """95 % percentile interval of the mean."""
    n = len(values)
    if n == 0:
        return [float("nan"), float("nan")]
    means = values[rng.integers(0, n, size=(resamples, n))].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return [round(float(low), 4), round(float(high), 4)]


# ------------------------------------------------------------------------------------ evaluation


def run_evaluation(settings: Settings, *, sample: int = 30) -> dict[str, Any]:
    marts, lake = settings.marts_dir, settings.lake_dir
    con = duckdb.connect(":memory:")
    for name, path in {
        "quotes": parquet_path(marts, "process_quotes"),
        "stats": parquet_path(marts, "process_quote_stats"),
        "signals": parquet_path(marts, "process_signals"),
    }.items():
        con.execute(f'CREATE VIEW "{name}" AS SELECT * FROM read_parquet({quote_literal(str(path))})')
    source = LakeQuoteSource(
        lake, marts, settings.texts_dir
    )  # parties only: faster, same eligibility to <0.1 %
    sweep_source = LakeQuoteSource(lake, marts, settings.texts_dir, raw_path=settings.ocds_bulk_path)
    vocabulary, lexicon = source.name_vocabulary(), source.lexicon()  # one pass over the texts, cached
    sweep_source._cached = source._cached
    rng = np.random.default_rng(SEED)
    summary = orjson.loads((marts / "process_quotes_build.json").read_bytes())
    calibration = [
        r[0]
        for r in con.execute(f"SELECT ocid FROM stats ORDER BY ocid LIMIT {CALIBRATION_PROCESSES}").fetchall()
    ]
    embedder = FastEmbedEmbedder()
    numbers: dict[str, Any] = {
        "seed": SEED,
        "similarity_floor": summary["floor"],
        "build": _build_numbers(summary, marts, con),
        "coverage": _coverage(con),
        "calibration": _calibration(source, embedder, calibration, vocabulary, lexicon),
        "retrieval_check": _retrieval_check(con, source, set(calibration), rng, vocabulary, lexicon),
        "privacy_sweep": _privacy_sweep(con, sweep_source, vocabulary, lexicon),
    }
    candidates = numbers["privacy_sweep"].pop("_candidate_sample")
    return {
        "numbers": numbers,
        "sample": _sample(con, sample, random.Random(SEED)),
        "name_candidates": [{"ocid": o, "text": t} for o, t in candidates],
    }


def _build_numbers(summary: dict[str, Any], marts: Path, con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    reasons = summary["exclusions_by_reason"]
    by_category = Counter()
    for key, count in reasons.items():
        by_category[key.split(":")[0]] += count
    return {
        "flagged_processes_with_text": summary["processes"],
        "texts": summary["texts"],
        "quotes": summary["quotes"],
        "quotes_with_pair": summary["quotes_with_pair"],
        "near_duplicates_skipped": summary["near_duplicates_skipped"],
        "exclusions_by_reason": reasons,
        "exclusions_by_category": dict(by_category),
        "wall_seconds": summary["wall_seconds"],
        "embed_seconds": summary["embed_seconds"],
        "processes_per_second": summary["processes_per_second"],
        "texts_per_second": summary["texts_per_second"],
        "bytes": {
            name: (marts / f"{name}.parquet").stat().st_size
            for name in ("process_quotes", "process_quote_stats")
        },
        "stats_rows": con.execute("SELECT count(*) FROM stats").fetchone()[0],
        "quote_rows": con.execute("SELECT count(*) FROM quotes").fetchone()[0],
        "quote_rows_by_kind": dict(
            con.execute("SELECT kind, count(*) FROM quotes GROUP BY 1 ORDER BY 1").fetchall()
        ),
        "quote_rows_by_rank": {
            str(rank): n
            for rank, n in con.execute("SELECT rank, count(*) FROM quotes GROUP BY 1 ORDER BY 1").fetchall()
        },
        "rows_truncated": con.execute("SELECT count(*) FROM quotes WHERE truncated").fetchone()[0],
    }


def _coverage(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    sql = """
    WITH f AS (SELECT DISTINCT ocid, signal_code FROM signals),
         q AS (SELECT DISTINCT ocid FROM quotes)
    SELECT {group} AS signal, count(*) AS flagged, count(s.ocid) AS with_text,
           count(*) FILTER (WHERE s.n_eligible > 0) AS with_eligible_text, count(q.ocid) AS with_quote
    FROM {source} LEFT JOIN stats s USING (ocid) LEFT JOIN q USING (ocid) {tail}
    """
    by_signal = con.execute(
        sql.format(group="f.signal_code", source="f", tail="GROUP BY 1 ORDER BY 1")
    ).fetchall()
    overall = con.execute(
        sql.format(group="'ALL'", source="(SELECT DISTINCT ocid FROM signals) f", tail="GROUP BY 1")
    ).fetchall()

    def row(values: tuple) -> dict[str, Any]:
        _, flagged, with_text, eligible, with_quote = values
        return {
            "flagged": flagged,
            "with_text": with_text,
            "with_eligible_text": eligible,
            "with_quote": with_quote,
            "share_with_quote": round(with_quote / flagged, 4) if flagged else None,
            "share_with_quote_among_with_text": round(with_quote / with_text, 4) if with_text else None,
        }

    return {"all_flagged": row(overall[0]), "by_signal": {v[0]: row(v) for v in by_signal}}


def _eligible_items(
    bundle: bq.ProcessBundle, vocabulary: frozenset[str] = frozenset(), lexicon: Lexicon | None = None
) -> list[bq.Item]:
    judged = bq.judge_texts(bundle, vocabulary, lexicon)
    eligible = {(j.row.kind, j.row.seq): j.row for j in judged if j.verdict.eligible}
    return bq._items(eligible, {key: (0.0, "") for key in eligible})


def _item_text(item: bq.Item) -> str:
    return norm(" ".join(m.text for m in item.members))


def _calibration(
    source: LakeQuoteSource,
    embedder: FastEmbedEmbedder,
    ocids: list[str],
    vocabulary: frozenset[str],
    lexicon: Lexicon,
) -> dict[str, Any]:
    codes, topics = bq.topic_vectors(embedder)
    rows: list[tuple[str, float, str]] = []
    best_all: list[float] = []
    bundles = list(source.bundles(ocids=ocids))
    judged = {
        b.ocid: [j for j in bq.judge_texts(b, vocabulary, lexicon) if j.verdict.eligible] for b in bundles
    }
    unique = sorted({j.row.text[: bq.EMBED_MAX_CHARS] for items in judged.values() for j in items})
    vectors = dict(zip(unique, embedder.embed(unique), strict=True))
    for bundle in bundles:
        fired = [i for i, c in enumerate(codes) if c in bundle.signals]
        for item in judged[bundle.ocid]:
            if not fired:
                continue
            vector = vectors[item.row.text[: bq.EMBED_MAX_CHARS]]
            sims = topics[fired] @ vector
            best_all.append(float(sims.max()))
            rows.extend(
                (codes[i], float(topics[i] @ vector), norm(item.row.text)) for i in fired if codes[i] in STEMS
            )
    hits = np.array([bool(STEMS[c].search(t)) for c, _, t in rows])
    sims = np.array([s for _, s, _ in rows])
    grid = {}
    for floor in FLOOR_GRID:
        mask = sims >= floor
        rate = float(hits[mask].mean()) if mask.any() else None
        grid[str(floor)] = {
            "passages": int(mask.sum()),
            "stem_rate": round(rate, 4) if rate is not None else None,
            "lift": round(rate / float(hits.mean()), 2) if rate is not None else None,
        }
    return {
        "processes": len(bundles),
        "eligible_passages": len(best_all),
        "best_similarity_percentiles": {
            str(p): round(float(np.percentile(best_all, p)), 3) for p in (5, 25, 50, 75, 90, 95, 99)
        },
        "stem_passage_pairs": len(rows),
        "base_stem_rate": round(float(hits.mean()), 4),
        "by_floor": grid,
        "rule": "smallest floor on the 0.05 grid whose stem rate is at least twice the base rate",
    }


def _retrieval_check(
    con: duckdb.DuckDBPyConnection,
    source: LakeQuoteSource,
    excluded: set[str],
    rng: np.random.Generator,
    vocabulary: frozenset[str],
    lexicon: Lexicon,
) -> dict[str, Any]:
    out: dict[str, Any] = {"evaluated_processes_exclude_calibration": True, "bootstrap_resamples": BOOTSTRAP}
    pyrandom = random.Random(SEED)
    for code, stem in STEMS.items():
        rows = con.execute(
            "SELECT q.ocid, q.text, coalesce(q.pair_text, '') FROM quotes q JOIN stats USING (ocid) "
            "WHERE q.related_signal = ? AND q.rank = (SELECT min(rank) FROM quotes q2 WHERE q2.ocid = q.ocid "
            "AND q2.related_signal = ?)",
            [code, code],
        ).fetchall()
        selected = {ocid: norm(f"{text} {pair}") for ocid, text, pair in rows if ocid not in excluded}
        selected_hit: list[bool] = []
        random_hit: list[bool] = []
        for bundle in source.bundles(ocids=sorted(selected)):
            items = _eligible_items(bundle, vocabulary, lexicon)
            if not items:
                continue
            selected_hit.append(bool(stem.search(selected[bundle.ocid])))
            random_hit.append(bool(stem.search(_item_text(pyrandom.choice(items)))))
        sel, rnd = np.array(selected_hit, dtype=float), np.array(random_hit, dtype=float)
        n = len(sel)
        index = rng.integers(0, max(n, 1), size=(BOOTSTRAP, max(n, 1)))
        diff = (sel[index].mean(axis=1) - rnd[index].mean(axis=1)) if n else np.array([float("nan")])
        out[code] = {
            "processes": n,
            "selected_quote_stem_rate": round(float(sel.mean()), 4) if n else None,
            "selected_ci95": bootstrap_ci(sel, rng),
            "random_eligible_item_stem_rate": round(float(rnd.mean()), 4) if n else None,
            "random_ci95": bootstrap_ci(rnd, rng),
            "difference": round(float((sel - rnd).mean()), 4) if n else None,
            "difference_ci95": [
                round(float(np.percentile(diff, 2.5)), 4),
                round(float(np.percentile(diff, 97.5)), 4),
            ],
        }
    return out


# ------------------------------------------------------------------------------- privacy sweep


def _all_rule_names() -> list[str]:
    return list(ALL_RULES)


def _privacy_sweep(
    con: duckdb.DuckDBPyConnection, source: LakeQuoteSource, vocabulary: frozenset[str], lexicon: Lexicon
) -> dict[str, Any]:
    rows = con.execute(
        "SELECT ocid, rank, text, coalesce(pair_text, '') FROM quotes ORDER BY ocid, rank"
    ).fetchall()
    ocids = {r[0] for r in rows}
    names: dict[str, set[str]] = {}
    protected: dict[str, tuple[str, ...]] = {}
    for bundle in source.bundles(ocids=sorted(ocids)):
        names[bundle.ocid] = set(bundle.person_names)
        protected[bundle.ocid] = bundle.protected_names
    # A weaker vocabulary (tokens of any natural-person name; the build uses tokens of at least 2 names)
    # estimates what the screen could still miss: pairs of rare given names and surnames.
    weak = source.name_vocabulary(min_persons=1)
    counts = Counter()
    hits: list[dict[str, Any]] = []
    candidates: list[tuple[str, str]] = []
    for ocid, rank, text, pair in rows:
        for label, passage in (("text", text), ("pair", pair)):
            if not passage:
                continue
            counts["passages"] += 1
            words = _tokens(passage)
            checks = {
                "identifier_scan": document_has_personal_identifier(passage),
                "name_search": any(_contains_name(words, _name_pairs(n)) for n in names.get(ocid, ())),
                "email": bool(_EMAIL.search(passage)),
                "phone": bool(_PHONE.search(passage) or _PHONE_CUE.search(norm(passage))),
                "senor_followed_by_a_name": bool(_SENOR_NAME.search(passage)),
            }
            for rule in rules_hit(blank_protected(passage, protected.get(ocid, ()))):
                counts[f"gate:{rule}"] += 1
            verdict = check_passage(
                passage,
                person_names=sorted(names.get(ocid, ())),
                protected_names=protected.get(ocid, ()),
                name_vocabulary=vocabulary,
                lexicon=lexicon,
            )
            if not verdict.eligible:
                counts["boundary_refusals"] += 1
            if probable_person_name(passage, weak, protected.get(ocid, ())):
                counts["rarer_name_pair_candidates"] += 1
                candidates.append((ocid, passage))
            for check, hit in checks.items():
                if hit:
                    counts[check] += 1
                    hits.append({"ocid": ocid, "rank": rank, "part": label, "check": check})
    return {
        "quote_passages_scanned": counts["passages"],
        "processes_with_quotes": len(ocids),
        "processes_with_person_names_searched": sum(1 for v in names.values() if v),
        "person_names_searched": sum(len(v) for v in names.values()),
        "hits": {
            check: counts[check]
            for check in ("identifier_scan", "name_search", "email", "phone", "senor_followed_by_a_name")
        },
        "gate_rule_hits": {
            name: counts[f"gate:{name}"]
            for name in (*REVIEWER_RULES, *sorted(set(_all_rule_names()) - set(REVIEWER_RULES)))
        },
        "boundary_refusals": counts["boundary_refusals"],
        "rarer_name_pair_candidates": counts["rarer_name_pair_candidates"],
        "hit_locations": hits[:200],
        "_candidate_sample": random.Random(SEED).sample(candidates, min(40, len(candidates))),
    }


def _sample(con: duckdb.DuckDBPyConnection, n: int, rng: random.Random) -> list[dict[str, Any]]:
    if not n:
        return []
    rows = con.execute(
        "SELECT ocid, related_signal, similarity, kind, text, coalesce(pair_text, '') FROM quotes"
    ).fetchall()
    chosen = rng.sample(rows, min(n, len(rows)))
    keys = ("ocid", "related_signal", "similarity", "kind", "text", "pair_text")
    return [dict(zip(keys, row, strict=True)) for row in chosen]


# ---------------------------------------------------------------------------- generated docs block

DOC_BEGIN = "<!-- BEGIN GENERATED: quotes -->"
DOC_END = "<!-- END GENERATED: quotes -->"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f} %"


def render_markdown(numbers: dict[str, Any], before: dict[str, Any] | None = None) -> str:
    """The measured numbers of `eval/quotes.json` as the generated block of docs/QUOTES.md."""
    build, cover = numbers["build"], numbers["coverage"]
    calibration, check, sweep = numbers["calibration"], numbers["retrieval_check"], numbers["privacy_sweep"]
    lines = [
        DOC_BEGIN,
        f"Generated by `veedor quotes evaluate` (seed {numbers['seed']}, "
        f"{check['bootstrap_resamples']} bootstrap resamples; intervals are 95 % percentile intervals).",
        "",
        "**Build** (`veedor quotes build`, one run over the whole lake):",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Flagged processes with at least one text | {build['flagged_processes_with_text']:,} |",
        f"| Texts screened | {build['texts']:,} |",
        f"| Quotes stored (items) | {build['quotes']:,} "
        f"({build['quotes_with_pair']:,} with a paired answer) |",
        f"| Items skipped as near-duplicates | {build['near_duplicates_skipped']:,} |",
        f"| Quotes by rank 1 / 2 / 3 | {build['quote_rows_by_rank']['1']:,} / "
        f"{build['quote_rows_by_rank'].get('2', 0):,} / {build['quote_rows_by_rank'].get('3', 0):,} |",
        f"| Quotes cut for display (`truncated`) | {build['rows_truncated']:,} |",
        f"| Wall time, embedding time | {build['wall_seconds']} s, {build['embed_seconds']} s "
        f"({build['processes_per_second']} processes/s, {build['texts_per_second']} texts/s) |",
        f"| Mart sizes | {build['bytes']['process_quotes'] / 1e6:.1f} MB quotes, "
        f"{build['bytes']['process_quote_stats'] / 1e6:.2f} MB per-process counts |",
        "",
        "**Coverage**: share of flagged processes with at least one quote, by signal. A process counts under "
        "every signal that fired on it.",
        "",
        "| Signal | Flagged | With text | With a quote | Share of flagged | Share before review 5 |",
        "|---|---|---|---|---|---|",
    ]
    old = (before or {}).get("coverage", {})

    def was(code: str) -> str:
        row = old.get("all_flagged" if code == "ALL" else "by_signal", {})
        row = row if code == "ALL" else row.get(code, {})
        return _pct(row.get("share_with_quote")) if row else "n/a"

    for code, row in cover["by_signal"].items():
        lines.append(
            f"| `{code}` | {row['flagged']:,} | {row['with_text']:,} | {row['with_quote']:,} | "
            f"{_pct(row['share_with_quote'])} | {was(code)} |"
        )
    total = cover["all_flagged"]
    lines += [
        f"| **All flagged** | {total['flagged']:,} | {total['with_text']:,} | {total['with_quote']:,} | "
        f"{_pct(total['share_with_quote'])} | {was('ALL')} |",
        "",
        "**Exclusions** (text rows; an answer whose question was withheld is `question_excluded`):",
        "",
        "| Category and reason | Rows |",
        "|---|---|",
    ]
    for reason, count in build["exclusions_by_reason"].items():
        lines.append(f"| {reason.replace(':', ' / ')} | {count:,} |")
    categories = build["exclusions_by_category"]
    lines += [
        f"| **personal data (total)** | {categories.get('personal', 0):,} |",
        f"| **unsafe wording or markup (total)** | {categories.get('unsafe', 0):,} |",
        "",
        "**Similarity floor** "
        f"({numbers['similarity_floor']}). Calibration sample: the first "
        f"{calibration['processes']:,} flagged processes by ocid "
        f"({calibration['eligible_passages']:,} eligible passages; best similarity to a fired signal: "
        f"median {calibration['best_similarity_percentiles']['50']}, "
        f"p90 {calibration['best_similarity_percentiles']['90']}). "
        f"Rule: {calibration['rule']}. Base rate of a deadline or price stem among passage-signal pairs: "
        f"{_pct(calibration['base_stem_rate'])}.",
        "",
        "| Floor | Passage-signal pairs | Stem rate | Lift over base |",
        "|---|---|---|---|",
    ]
    for floor, row in calibration["by_floor"].items():
        lines.append(f"| {floor} | {row['passages']:,} | {_pct(row['stem_rate'])} | {row['lift']} |")
    lines += [
        "",
        "**Retrieval check without labels** (processes outside the calibration sample; the selected quote of "
        "the signal against one random eligible item of the same process):",
        "",
        "| Signal and stems | Processes | Selected quote | Random eligible item | Difference |",
        "|---|---|---|---|---|",
    ]
    stems_by_code = {
        "SHORT_TENDER_WINDOW": "plazo, prórroga, días, fecha, ampli-",
        "LOW_SAVING": "precio, presupuesto, valor, monto, descuento, costo, puja, rebaja",
    }
    for code, stems in stems_by_code.items():
        row = check[code]
        lines.append(
            f"| `{code}` ({stems}) | {row['processes']:,} | {_pct(row['selected_quote_stem_rate'])} "
            f"[{row['selected_ci95'][0] * 100:.1f}, {row['selected_ci95'][1] * 100:.1f}] | "
            f"{_pct(row['random_eligible_item_stem_rate'])} "
            f"[{row['random_ci95'][0] * 100:.1f}, {row['random_ci95'][1] * 100:.1f}] | "
            f"{row['difference'] * 100:+.1f} points "
            f"[{row['difference_ci95'][0] * 100:+.1f}, {row['difference_ci95'][1] * 100:+.1f}] |"
        )
    hits = sweep["hits"]
    lines += [
        "",
        "**Privacy sweep over every stored quote** "
        f"({sweep['quote_passages_scanned']:,} passages in {sweep['processes_with_quotes']:,} processes):",
        "",
        "| Check | Hits |",
        "|---|---|",
        f"| Identifier scan (natural-person RUC, valid cédula) | {hits['identifier_scan']} |",
        "| Name search: two consecutive tokens of any natural-person or RUC-less party, tenderer, supplier "
        f"or enquiry asker of the same process, either order ({sweep['person_names_searched']:,} names) | "
        f"{hits['name_search']} |",
        f"| Telephone numbers | {hits['phone']} |",
        f"| E-mail addresses | {hits['email']} |",
        f"| «Señor/Señora» followed by a name | {hits['senor_followed_by_a_name']} |",
        f"| Passages with a pair of rarer given-name or surname tokens (candidates, mostly places and "
        f"institutions) | {sweep['rarer_name_pair_candidates']} |",
        f"| Passages the deny-by-default boundary function refuses today (same function as the API) | "
        f"{sweep['boundary_refusals']} |",
        "",
        "**Release-gate rules** (`scripts/check_quotes_privacy.py`; the first seven are the reviewer's "
        "regular expressions, the rest are this project's; every one must be 0):",
        "",
        "| Rule | Hits |",
        "|---|---|",
        *[f"| `{name}` | {count} |" for name, count in sweep["gate_rule_hits"].items()],
        DOC_END,
    ]
    return "\n".join(lines)


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
