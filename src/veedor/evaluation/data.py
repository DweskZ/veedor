"""DuckDB access for the evaluation: one process-level table and supplier-level aggregations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import duckdb
import numpy as np

KIND_COMPANY = "company"
KIND_NATURAL = "natural_person"
LAKE_TABLES = ("processes", "ghost_companies", "company_financials")
MART_TABLES = ("process_scores", "process_signals")


def connect(lake_dir: Path, marts_dir: Path) -> duckdb.DuckDBPyConnection:
    """In-memory connection with a view per Parquet table used by the evaluation."""
    con = duckdb.connect()
    for name, directory in [(t, lake_dir) for t in LAKE_TABLES] + [(t, marts_dir) for t in MART_TABLES]:
        path = directory / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}. Build the lake and the marts first.")
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')")
    return con


def flag(code: str) -> str:
    return f"f_{code.lower()}"


def build_process_table(
    con: duckdb.DuckDBPyConnection, codes: Iterable[str], context_codes: Iterable[str] = ()
) -> None:
    """Create `eval_process`: one row per scored process with one boolean column per signal.

    Risk flags come from `process_signals` rows with `kind = 'risk'` (the only ones that score);
    context flags come from rows with `kind = 'context'` and never enter a score. The method key
    collapses every catalogue convention into one stratum.
    """
    flags = [f"coalesce(list_contains(r.codes, '{c}'), false) AS {flag(c)}" for c in codes] + [
        f"coalesce(list_contains(x.codes, '{c}'), false) AS {flag(c)}" for c in context_codes
    ]
    con.execute(
        f"""
        CREATE OR REPLACE TABLE eval_process AS
        WITH r AS (
          SELECT ocid, list(DISTINCT signal_code) AS codes FROM process_signals
          WHERE kind = 'risk' GROUP BY ocid),
        x AS (
          SELECT ocid, list(DISTINCT signal_code) AS codes FROM process_signals
          WHERE kind = 'context' GROUP BY ocid)
        SELECT s.ocid, s.winner_ruc, s.winner_name, s.winner_kind, s.year, s.buyer_ruc, s.buyer_name,
          s.method, p.method_group,
          CASE WHEN p.method_group = 'catalogue' THEN 'catalogue'
               ELSE coalesce(s.method, 'unknown') END AS method_key,
          s.award_total, s.anomaly_score, s.risk_score,
          TRY_CAST(substr(coalesce(p.first_award_date, p.date_signed, p.release_date), 1, 10) AS DATE)
            AS award_date,
          {", ".join(flags)}
        FROM process_scores s
        JOIN processes p USING (ocid)
        LEFT JOIN r USING (ocid)
        LEFT JOIN x USING (ocid)
        """
    )


def score_sql(weights: Mapping[str, float], excluded: Iterable[str] = (), cap: float = 100.0) -> str:
    """SQL expression for a weighted-sum score over the signals not excluded, capped."""
    drop = set(excluded)
    terms = [f"{weight} * {flag(code)}::int" for code, weight in weights.items() if code not in drop]
    return f"least({cap}, {' + '.join(terms) if terms else '0'})::DOUBLE"


def _kinds_sql(kinds: Iterable[str]) -> str:
    return ", ".join(f"'{k}'" for k in kinds)


def _fetch(con: duckdb.DuckDBPyConnection, sql: str) -> dict[str, np.ndarray]:
    return {k: np.asarray(v) for k, v in con.execute(sql).fetchnumpy().items()}


def supplier_table(
    con: duckdb.DuckDBPyConnection,
    score: str,
    *,
    kinds: Iterable[str] = (KIND_COMPANY,),
    temporal: bool = False,
    scored_only: bool = False,
    exclude_buyer: str | None = None,
) -> dict[str, np.ndarray]:
    """One row per awarded supplier: label, process count, score aggregates and amount."""
    keep = "WHERE (NOT pos OR (notif IS NOT NULL AND award_date < notif))" if temporal else ""
    scored = "AND e.anomaly_score IS NOT NULL" if scored_only else ""
    if exclude_buyer is not None:
        scored += f" AND e.buyer_ruc IS DISTINCT FROM '{exclude_buyer.replace("'", "''")}'"
    return _fetch(
        con,
        f"""
        WITH p AS (
          SELECT e.*, (g.ruc IS NOT NULL) AS pos, TRY_CAST(g.notification_date AS DATE) AS notif,
                 {score} AS score
          FROM eval_process e LEFT JOIN ghost_companies g ON g.ruc = e.winner_ruc
          WHERE e.winner_ruc IS NOT NULL AND e.winner_kind IN ({_kinds_sql(kinds)}) {scored}
        )
        SELECT winner_ruc AS ruc, any_value(winner_name) AS name, bool_or(pos) AS label,
               count(*) AS n_processes, avg(score) AS score_mean, max(score) AS score_max,
               avg((score > 0)::DOUBLE) AS score_share, coalesce(sum(award_total), 0) AS amount,
               avg(anomaly_score) AS anomaly_mean, max(anomaly_score) AS anomaly_max
        FROM p {keep} GROUP BY winner_ruc ORDER BY winner_ruc
        """,
    )


def signal_counts(
    con: duckdb.DuckDBPyConnection,
    codes: Iterable[str],
    *,
    temporal: bool,
    non_catalogue: bool,
) -> dict[str, np.ndarray]:
    """Per company supplier: label, process count and number of processes where each signal fired."""
    sums = ", ".join(f"sum({flag(c)}::INT) AS n_{c.lower()}" for c in codes)
    keep = "AND (NOT pos OR (notif IS NOT NULL AND award_date < notif))" if temporal else ""
    scope = "AND e.method_group <> 'catalogue'" if non_catalogue else ""
    return _fetch(
        con,
        f"""
        WITH p AS (
          SELECT e.*, (g.ruc IS NOT NULL) AS pos, TRY_CAST(g.notification_date AS DATE) AS notif
          FROM eval_process e LEFT JOIN ghost_companies g ON g.ruc = e.winner_ruc
          WHERE e.winner_ruc IS NOT NULL AND e.winner_kind = '{KIND_COMPANY}' {scope}
        )
        SELECT winner_ruc AS ruc, bool_or(pos) AS label, count(*) AS n_processes, {sums}
        FROM p WHERE TRUE {keep} GROUP BY winner_ruc ORDER BY winner_ruc
        """,
    )


def labelled_processes(
    con: duckdb.DuckDBPyConnection, score: str, *, temporal: bool
) -> dict[str, np.ndarray]:
    """Processes won by labelled company suppliers, with their stratum, buyer and score."""
    keep = "AND g.notification_date IS NOT NULL AND award_date < TRY_CAST(g.notification_date AS DATE)"
    return _fetch(
        con,
        f"""
        SELECT e.ocid, e.winner_ruc AS ruc, e.year, e.method_key, e.buyer_ruc,
               e.award_date, {score} AS score
        FROM eval_process e JOIN ghost_companies g ON g.ruc = e.winner_ruc
        WHERE e.winner_kind = '{KIND_COMPANY}' {keep if temporal else ""}
        ORDER BY e.ocid
        """,
    )


def unlabelled_strata(con: duckdb.DuckDBPyConnection, score: str) -> dict[str, np.ndarray]:
    """Counts of unlabelled company-won processes by (method key, year, score)."""
    return _fetch(
        con,
        f"""
        SELECT e.method_key, e.year, {score} AS score, count(*) AS n
        FROM eval_process e ANTI JOIN ghost_companies g ON g.ruc = e.winner_ruc
        WHERE e.winner_kind = '{KIND_COMPANY}' AND e.winner_ruc IS NOT NULL
        GROUP BY ALL
        """,
    )
