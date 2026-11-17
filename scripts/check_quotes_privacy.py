#!/usr/bin/env python3
"""Release gate: fail (exit 1) when the quotes mart still holds anything the screens should have removed.

    uv run python scripts/check_quotes_privacy.py [--marts DIR] [--lake DIR] [--max-report N]

Two checks, both over every stored passage (the quote and its paired answer):

1. content rules (`veedor.domain.quotes.gate`): the seven regular expressions of the fifth review plus this
   project's own patterns. Any match is a failure;
2. the deny-by-default boundary function (`check_passage` with the quote lexicon, the person-name vocabulary
   when present and the real protected names of each process from the lake): any passage it would refuse
   today is a failure, so a mart built with older rules can never ship.

A missing mart, a missing lexicon or a mart without a pair of tables is a failure too (fail closed). The
output
never prints a passage or a name: only rule names, counts and short hashes of the offending passages.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

from veedor.domain.quotes.gate import rules_hit
from veedor.domain.quotes.lexicon import Lexicon
from veedor.domain.quotes.screen import check_passage
from veedor.domain.quotes.strict import blank_protected
from veedor.use_cases.build_quotes import name_context

QUOTES, LEXICON, VOCABULARY = "process_quotes", "quote_lexicon", "person_name_tokens"


def _short(text: str) -> str:
    return hashlib.sha256(" ".join(text.casefold().split()).encode()).hexdigest()[:10]


def _party_rows(con: duckdb.DuckDBPyConnection, lake: Path, marts: Path) -> dict[str, list[tuple]]:
    """``ocid -> [(ruc, name, kind)]`` for each process with a stored quote (buyer included, kind 'buyer')."""
    out: dict[str, list[tuple]] = defaultdict(list)
    scores = marts / "process_scores.parquet"
    sources = [
        (
            "tenderers",
            "SELECT ocid, supplier_ruc, supplier_name, NULL FROM read_parquet(?)",
            lake / "tenderers.parquet",
        ),
        (
            "awards",
            "SELECT ocid, supplier_ruc, supplier_name, NULL FROM read_parquet(?)",
            lake / "awards.parquet",
        ),
        ("scores", "SELECT ocid, winner_ruc, winner_name, winner_kind FROM read_parquet(?)", scores),
        (
            "buyers",
            "SELECT ocid, buyer_ruc, buyer_name, 'buyer' FROM read_parquet(?)",
            lake / "processes.parquet",
        ),
    ]
    for _, sql, path in sources:
        if not path.is_file():
            continue
        rows = con.execute(
            f"SELECT t.* FROM ({sql}) t WHERE t.ocid IN (SELECT DISTINCT ocid FROM quotes)", [str(path)]
        ).fetchall()
        for ocid, ruc, name, kind in rows:
            out[ocid].append((ruc, name, kind))
    return out


def run(marts: Path, lake: Path, max_report: int = 10) -> int:
    quotes_path = marts / f"{QUOTES}.parquet"
    lexicon_path = marts / f"{LEXICON}.parquet"
    if not quotes_path.is_file():
        print(f"FAIL: {quotes_path} not found (fail closed)")
        return 1
    if not lexicon_path.is_file():
        print(f"FAIL: {lexicon_path} not found: the deny-by-default screen cannot be re-run (fail closed)")
        return 1
    con = duckdb.connect(":memory:")
    literal = str(quotes_path).replace("'", "''")
    con.execute(f"CREATE VIEW quotes AS SELECT * FROM read_parquet('{literal}')")
    lex_rows = con.execute("SELECT token, form FROM read_parquet(?)", [str(lexicon_path)]).fetchall()
    lexicon = Lexicon(
        frozenset(t for t, f in lex_rows if f == "capitalised"),
        frozenset(t for t, f in lex_rows if f == "lowercase"),
    )
    vocab_path = marts / f"{VOCABULARY}.parquet"
    vocabulary = (
        frozenset(
            r[0] for r in con.execute("SELECT token FROM read_parquet(?)", [str(vocab_path)]).fetchall()
        )
        if vocab_path.is_file()
        else frozenset()
    )
    parties = _party_rows(con, lake, marts) if lake.is_dir() else {}
    rows = con.execute("SELECT ocid, text, pair_text FROM quotes").fetchall()

    rule_counts: Counter[str] = Counter()
    boundary: Counter[str] = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    passages = 0
    flagged: set[str] = set()
    for ocid, text, pair_text in rows:
        buyer = next(((r, n) for r, n, k in parties.get(ocid, ()) if k == "buyer"), (None, None))
        persons, protected = name_context(
            [(r, n, k) for r, n, k in parties.get(ocid, ()) if k != "buyer"], buyer[0], buyer[1]
        )
        for passage in (text, pair_text):
            if not passage:
                continue
            passages += 1
            for rule in rules_hit(blank_protected(passage, protected)):
                rule_counts[rule] += 1
                flagged.add(_short(passage))
                if len(samples[rule]) < max_report:
                    samples[rule].append(f"{ocid[-16:]}:{_short(passage)}")
            verdict = check_passage(
                passage,
                person_names=persons,
                protected_names=protected,
                name_vocabulary=vocabulary,
                lexicon=lexicon,
            )
            if not verdict.eligible:
                boundary[f"{verdict.category}:{verdict.reason}"] += 1
                flagged.add(_short(passage))
                if len(samples["boundary"]) < max_report:
                    samples["boundary"].append(f"{ocid[-16:]}:{_short(passage)}:{verdict.reason}")

    print(
        f"passages checked: {passages:,} in {len(rows):,} stored quotes; "
        f"lexicon {len(lexicon.capitalised):,} + {len(lexicon.lowercase):,} tokens; "
        f"vocabulary {'present' if vocabulary else 'absent'}; "
        f"protected names from lake {'yes' if parties else 'NO'}"
    )
    from veedor.domain.quotes.gate import REVIEWER_RULES

    print("reviewer rules (must be 0):")
    for name in REVIEWER_RULES:
        print(f"  {name}: {rule_counts[name]}")
    print("own rules (must be 0):")
    for name in sorted(set(rule_counts) - set(REVIEWER_RULES)):
        print(f"  {name}: {rule_counts[name]}")
    if not (set(rule_counts) - set(REVIEWER_RULES)):
        print("  (none matched)")
    print(f"boundary re-check refusals (must be 0): {sum(boundary.values())} {dict(boundary)}")
    if not parties:
        print("FAIL: the lake was not found, so the protected names could not be loaded (fail closed)")
        return 1
    failed = bool(rule_counts) or bool(boundary)
    if failed:
        print(f"FAIL: {len(flagged)} distinct passages would be refused. Samples (ocid tail:hash):")
        for key, items in samples.items():
            print(f"  {key}: {items}")
        return 1
    print("OK: no passage matches any gate rule and the boundary function accepts every stored passage")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--marts", type=Path, default=root / "data" / "marts")
    parser.add_argument("--lake", type=Path, default=root / "data" / "lake")
    parser.add_argument("--max-report", type=int, default=10)
    args = parser.parse_args()
    return run(args.marts, args.lake, args.max_report)


if __name__ == "__main__":
    sys.exit(main())
