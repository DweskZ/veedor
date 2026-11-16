"""Descriptive coverage of the signals. No labels involved."""

from __future__ import annotations

from itertools import combinations_with_replacement
from pathlib import Path
from typing import Any

import duckdb

from veedor.domain.signals.scoring import SIGNAL_WEIGHTS
from veedor.evaluation import data
from veedor.evaluation.backtest import CONTEXT_CODES, VARIANTS

SCORE_QUANTILES = (0.5, 0.9, 0.99, 0.999)


def _any_signal_sql() -> str:
    return " OR ".join(data.flag(c) for c in SIGNAL_WEIGHTS)


def _by(con: duckdb.DuckDBPyConnection, column: str) -> list[dict[str, Any]]:
    held_out = " OR ".join(data.flag(c) for c in SIGNAL_WEIGHTS if c not in VARIANTS["A"][1])
    rows = con.execute(
        f"""
        SELECT {column} AS k, count(*), sum(({_any_signal_sql()})::INT), sum(({held_out})::INT)
        FROM eval_process GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    return [
        {
            "key": k,
            "n_processes": int(n),
            "with_any_signal": int(a),
            "share_any": a / n,
            "share_any_held_out": h / n,
        }
        for k, n, a, h in rows
    ]


def _distribution(con: duckdb.DuckDBPyConnection, expression: str) -> dict[str, Any]:
    values = con.execute(
        f"SELECT ({expression})::DOUBLE AS s, count(*) FROM eval_process GROUP BY 1 ORDER BY 1"
    ).fetchall()
    total = sum(c for _, c in values)
    quantiles = {}
    for q in SCORE_QUANTILES:
        running = 0
        for v, c in values:
            running += c
            if running / total >= q:
                quantiles[str(q)] = v
                break
    return {
        "n_processes": total,
        "share_zero": sum(c for v, c in values if v == 0) / total,
        "max": values[-1][0],
        "quantiles": quantiles,
        "histogram": [{"score": v, "n_processes": c} for v, c in values],
    }


def _cooccurrence(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    codes = list(SIGNAL_WEIGHTS)
    pairs = list(combinations_with_replacement(codes, 2))
    sums = ", ".join(f"sum(({data.flag(a)} AND {data.flag(b)})::INT)" for a, b in pairs)
    row = con.execute(f"SELECT count(*), {sums} FROM eval_process").fetchone()
    counts = {f"{a}|{b}": int(v) for (a, b), v in zip(pairs, row[1:], strict=True)}
    return {"n_processes": row[0], "codes": codes, "counts": counts}


def _context(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Context signals (weight 0, outside the score): firings and overlap with risk signals."""
    fired = {
        c: int(con.execute(f"SELECT sum({data.flag(c)}::INT) FROM eval_process").fetchone()[0])
        for c in CONTEXT_CODES
    }
    any_context = " OR ".join(data.flag(c) for c in CONTEXT_CODES)
    both = f"(({any_context}) AND ({_any_signal_sql()}))"
    n_context, n_both = con.execute(
        f"SELECT sum(({any_context})::INT), sum({both}::INT) FROM eval_process"
    ).fetchone()
    return {"fired": fired, "n_with_any_context": int(n_context), "n_with_context_and_risk": int(n_both)}


def run_coverage(lake_dir: Path, marts_dir: Path) -> dict[str, Any]:
    con = data.connect(lake_dir, marts_dir)
    data.build_process_table(con, SIGNAL_WEIGHTS, CONTEXT_CODES)
    n = con.execute("SELECT count(*) FROM eval_process").fetchone()[0]
    fired = {
        c: int(con.execute(f"SELECT sum({data.flag(c)}::INT) FROM eval_process").fetchone()[0])
        for c in SIGNAL_WEIGHTS
    }
    return {
        "n_processes": n,
        "n_with_any_signal": int(
            con.execute(f"SELECT sum(({_any_signal_sql()})::INT) FROM eval_process").fetchone()[0]
        ),
        "signals_fired": fired,
        "context_signals": _context(con),
        "by_method_group": _by(con, "method_group"),
        "by_year": _by(con, "year"),
        "cooccurrence": _cooccurrence(con),
        "risk_score_distribution": _distribution(con, "risk_score"),
        "held_out_score_distribution": _distribution(con, data.score_sql(SIGNAL_WEIGHTS, VARIANTS["A"][1])),
    }


def summary_text(result: dict[str, Any]) -> str:
    n, any_n = result["n_processes"], result["n_with_any_signal"]
    lines = [f"Processes: {n:,}; with at least one signal: {any_n:,} ({any_n / n:.1%})", "By method group:"]
    for r in result["by_method_group"]:
        lines.append(f"  {r['key']}: {r['n_processes']:,} processes, {r['share_any']:.1%} with a signal")
    lines.append("By year (share with a signal):")
    lines.append("  " + ", ".join(f"{r['key']}: {r['share_any']:.1%}" for r in result["by_year"]))
    dist = result["risk_score_distribution"]
    lines.append(
        f"risk_score: {dist['share_zero']:.1%} at 0; quantiles {dist['quantiles']}; max {dist['max']}"
    )
    return "\n".join(lines)
