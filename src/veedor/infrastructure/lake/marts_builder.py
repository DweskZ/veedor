"""Build the Signals v1 marts from the Parquet lake with DuckDB.

Everything is set-based SQL over Parquet (see `marts_builder_sql`); Python only sequences the
statements, gates registry-dependent signals on the presence of their source tables and writes
the Parquet marts and the build summary.
"""

from __future__ import annotations

import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import orjson

from veedor.domain.signals import MAX_SCORE, SIGNAL_WEIGHTS, SIGNALS
from veedor.domain.signals import definitions as d
from veedor.domain.signals import parameters as p
from veedor.infrastructure.lake import marts_builder_sql as q
from veedor.infrastructure.lake.connection import (
    CORE_TABLES,
    connect_lake,
    existing_tables,
    quote_literal,
    view_columns,
)
from veedor.infrastructure.lake.marts_builder_anomaly import compute_anomaly_scores

SUMMARY_NAME = "build_summary.json"
MISSING_TABLE = "not computed: source table missing"


class LakeNotFoundError(RuntimeError):
    """Raised when a core lake table is absent, so no mart can be built."""


Params = dict[str, Any]


def _run(con: duckdb.DuckDBPyConnection, sql: str, params: Params | None = None) -> None:
    if params:
        con.execute(sql, params)
    else:
        con.execute(sql)


def _registry_gate(
    con: duckdb.DuckDBPyConnection, available: set[str], table: str, needed: set[str]
) -> str | None:
    """Reason to skip a registry-dependent signal, or None when its inputs are usable."""
    if table not in available:
        return f"{MISSING_TABLE} ({table}.parquet)"
    missing = needed - view_columns(con, table)
    if missing:
        return f"not computed: source column missing ({table}.{', '.join(sorted(missing))})"
    if con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] == 0:
        return f"not computed: source table empty ({table}.parquet)"
    return None


def _optional(columns: set[str], name: str, cast: str = "VARCHAR") -> str:
    return f'CAST("{name}" AS {cast})' if name in columns else f"CAST(NULL AS {cast})"


def _prepare_sri(con: duckdb.DuckDBPyConnection) -> None:
    cols = view_columns(con, "suppliers_sri")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE sri AS
        SELECT CAST(ruc AS VARCHAR) AS ruc,
               {_optional(cols, "status")} AS status,
               TRY_CAST(substr({_optional(cols, "activity_start_date")}, 1, 10) AS DATE) AS activity_start,
               {_optional(cols, "suspension_date")} AS suspension_date,
               {_optional(cols, "restart_date")} AS restart_date
        FROM suppliers_sri WHERE ruc IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY ruc ORDER BY activity_start DESC NULLS LAST) = 1
    """)


def _prepare_ghosts(con: duckdb.DuckDBPyConnection) -> None:
    cols = view_columns(con, "ghost_companies")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ghosts AS
        SELECT CAST(ruc AS VARCHAR) AS ruc,
               {_optional(cols, "resolution")} AS resolution,
               {_optional(cols, "notification_date")} AS notification_date,
               TRY_CAST(substr({_optional(cols, "notification_date")}, 1, 10) AS DATE) AS notification_day,
               {_optional(cols, "qualification_detail")} AS qualification_detail,
               {_optional(cols, "challenge_state")} AS challenge_state
        FROM ghost_companies WHERE ruc IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY ruc ORDER BY notification_day DESC NULLS LAST) = 1
    """)


def _prepare_financials(con: duckdb.DuckDBPyConnection) -> None:
    """One row per (ruc, year): the largest positive sales revenue (revenue <= 0 is unknown)."""
    con.execute("""
        CREATE OR REPLACE TEMP TABLE financials AS
        SELECT CAST(ruc AS VARCHAR) AS ruc, CAST(year AS INTEGER) AS year, max(revenue) AS revenue
        FROM company_financials
        WHERE ruc IS NOT NULL AND revenue > 0 AND year IS NOT NULL
        GROUP BY 1, 2
    """)


def _prepare_statistical(con: duckdb.DuckDBPyConnection) -> None:
    competitive = {"competitive": p.COMPETITIVE_GROUP}
    _run(con, q.SHORT_WINDOW_TABLE, competitive)
    _run(
        con,
        q.SHORT_WINDOW_THRESHOLDS,
        {"percentile": p.SHORT_WINDOW_PERCENTILE, "min_group": p.MIN_GROUP_SIZE},
    )
    _run(con, q.LOW_SAVING_TABLE, competitive)
    _run(
        con,
        q.LOW_SAVING_THRESHOLDS,
        {
            "percentile": p.LOW_SAVING_PERCENTILE,
            "min_ratio": p.LOW_SAVING_MIN_RATIO,
            "min_group": p.MIN_GROUP_SIZE,
            "max_share": p.LOW_SAVING_MAX_SHARE,
        },
    )


def _signal_statements() -> dict[str, tuple[str, Params]]:
    window = str(p.REPEATED_DIRECT_WINDOW_DAYS)
    return {
        d.SINGLE_BIDDER: (
            q.SINGLE_BIDDER,
            {"competitive": p.COMPETITIVE_GROUP, "max_tenderers": float(p.SINGLE_BIDDER_TENDERERS)},
        ),
        d.SHORT_TENDER_WINDOW: (q.SHORT_TENDER_WINDOW, {}),
        d.LOW_SAVING: (q.LOW_SAVING, {}),
        d.BUYER_CONCENTRATION: (
            q.BUYER_CONCENTRATION,
            {
                "catalogue": p.CATALOGUE_GROUP,
                "min_total": p.BUYER_CONCENTRATION_MIN_TOTAL,
                "min_awards": p.BUYER_CONCENTRATION_MIN_AWARDS,
                "min_share": p.BUYER_CONCENTRATION_MIN_SHARE,
            },
        ),
        d.REPEATED_DIRECT_AWARDS: (
            q.REPEATED_DIRECT_AWARDS.replace("__WINDOW_DAYS__", window),
            {
                "direct": p.DIRECT_GROUP,
                "cpc_prefix": p.REPEATED_DIRECT_CPC_PREFIX,
                "window_days": p.REPEATED_DIRECT_WINDOW_DAYS,
                "min_processes": float(p.REPEATED_DIRECT_MIN_PROCESSES),
            },
        ),
        d.RECURRING_COBIDDERS: (
            q.RECURRING_COBIDDERS,
            {"competitive": p.COMPETITIVE_GROUP, "min_meetings": float(p.RECURRING_COBIDDERS_MIN_MEETINGS)},
        ),
        d.NEW_SUPPLIER: (
            q.NEW_SUPPLIER,
            {"catalogue": p.CATALOGUE_GROUP, "max_days": p.NEW_SUPPLIER_MAX_DAYS},
        ),
        d.SUPPLIER_NOT_ACTIVE: (
            q.SUPPLIER_NOT_ACTIVE,
            {"catalogue": p.CATALOGUE_GROUP, "active_statuses": sorted(p.ACTIVE_STATUSES)},
        ),
        d.GHOST_COMPANY_LIST: (q.GHOST_COMPANY_LIST, {}),
        d.GHOST_COMPANY_LISTED_LATER: (q.GHOST_COMPANY_LISTED_LATER, {}),
        d.CONTRACT_VS_COMPANY_SIZE: (q.CONTRACT_VS_COMPANY_SIZE, {"factor": p.CONTRACT_SIZE_FACTOR}),
        d.CONTRACT_VS_COMPANY_SIZE_SAME_YEAR: (
            q.CONTRACT_VS_COMPANY_SIZE_SAME_YEAR,
            {"factor": p.CONTRACT_SIZE_FACTOR},
        ),
    }


# Context signals share the source tables (and therefore the gate) of their risk counterpart.
CONTEXT_PARENT = {
    d.GHOST_COMPANY_LISTED_LATER: d.GHOST_COMPANY_LIST,
    d.CONTRACT_VS_COMPANY_SIZE_SAME_YEAR: d.CONTRACT_VS_COMPANY_SIZE,
}


def _registry_skips(con: duckdb.DuckDBPyConnection, available: set[str]) -> dict[str, str]:
    """Gate every registry-dependent signal; prepare the helper tables of the ones that can run."""
    gates = {
        d.NEW_SUPPLIER: _registry_gate(con, available, "suppliers_sri", {"ruc", "activity_start_date"}),
        d.SUPPLIER_NOT_ACTIVE: _registry_gate(con, available, "suppliers_sri", {"ruc", "status"}),
        d.GHOST_COMPANY_LIST: _registry_gate(con, available, "ghost_companies", {"ruc"}),
        d.CONTRACT_VS_COMPANY_SIZE: _registry_gate(
            con, available, "company_financials", {"ruc", "year", "revenue"}
        ),
    }
    skipped = {code: reason for code, reason in gates.items() if reason}
    if not {d.NEW_SUPPLIER, d.SUPPLIER_NOT_ACTIVE} <= set(skipped):
        _prepare_sri(con)
    if d.GHOST_COMPANY_LIST not in skipped:
        _prepare_ghosts(con)
    if d.CONTRACT_VS_COMPANY_SIZE not in skipped:
        _prepare_financials(con)
        _run(con, q.SIZE_PICK, {"catalogue": p.CATALOGUE_GROUP, "factor": p.CONTRACT_SIZE_FACTOR})
    for context, parent in CONTEXT_PARENT.items():
        if parent in skipped:
            skipped[context] = skipped[parent]
    return skipped


def _table_counts(con: duckdb.DuckDBPyConnection, tables: list[str]) -> dict[str, int]:
    return {t: con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}


def _threshold_rows(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    cursor = con.execute(
        "SELECT signal_code, method, year, n, percentile_value, threshold, share_flagged, status "
        "FROM thresholds ORDER BY signal_code, method, year"
    )
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def _registry_coverage(con: duckdb.DuckDBPyConnection, skipped: dict[str, str]) -> dict[str, Any]:
    """How many non-catalogue winners could be matched to each registry table."""
    total = con.execute(
        "SELECT count(*) FROM base b JOIN winners w USING (ocid) "
        "WHERE b.method_group <> ? AND w.supplier_ruc IS NOT NULL",
        [p.CATALOGUE_GROUP],
    ).fetchone()[0]
    coverage: dict[str, Any] = {"non_catalogue_processes_with_winner_ruc": total}
    sources = {
        "suppliers_sri": ("sri", {d.NEW_SUPPLIER, d.SUPPLIER_NOT_ACTIVE}),
        "ghost_companies": ("ghosts", {d.GHOST_COMPANY_LIST}),
        "company_financials": ("financials", {d.CONTRACT_VS_COMPANY_SIZE}),
    }
    for source, (temp, codes) in sources.items():
        if codes <= set(skipped):
            continue
        matched = con.execute(
            f"SELECT count(*) FROM base b JOIN winners w USING (ocid) JOIN {temp} r "
            "ON r.ruc = w.supplier_ruc WHERE b.method_group <> ?",
            [p.CATALOGUE_GROUP],
        ).fetchone()[0]
        coverage[source] = {"matched_processes": matched}
    return coverage


def _excluded_individuals(con: duckdb.DuckDBPyConnection, skipped: dict[str, str]) -> dict[str, Any]:
    """Registry matches left out because the winner is a natural person or has no valid RUC."""
    out: dict[str, Any] = {}
    if d.GHOST_COMPANY_LIST not in skipped:
        risk, context = con.execute(q.EXCLUDED_GHOST).fetchone()
        out[d.GHOST_COMPANY_LIST] = {
            "excluded_natural_or_unidentified_winners": {"would_be_risk": risk, "would_be_context": context}
        }
    if d.SUPPLIER_NOT_ACTIVE not in skipped:
        params = [p.CATALOGUE_GROUP, sorted(p.ACTIVE_STATUSES)]
        n = con.execute(
            q.EXCLUDED_NOT_ACTIVE.replace("$catalogue", "?").replace("$active_statuses", "?"), params
        )
        out[d.SUPPLIER_NOT_ACTIVE] = {"excluded_natural_or_unidentified_winners": n.fetchone()[0]}
    if d.NEW_SUPPLIER not in skipped:
        n = con.execute(
            q.EXCLUDED_NEW_SUPPLIER.replace("$catalogue", "?").replace("$max_days", "?"),
            [p.CATALOGUE_GROUP, p.NEW_SUPPLIER_MAX_DAYS],
        )
        out[d.NEW_SUPPLIER] = {"excluded_natural_or_unidentified_winners": n.fetchone()[0]}
    return out


def _signal_details(con: duckdb.DuckDBPyConnection, skipped: dict[str, str]) -> dict[str, Any]:
    """Breakdowns of fired signals that readers need to interpret them."""
    timing = con.execute(
        "SELECT json_extract_string(evidence_json, '$.timing'), count(*) FROM signal_rows "
        "WHERE signal_code = 'SUPPLIER_NOT_ACTIVE' GROUP BY 1"
    ).fetchall()
    low_revenue = con.execute(
        "SELECT count(*) FROM signal_rows WHERE signal_code = 'CONTRACT_VS_COMPANY_SIZE' "
        "AND CAST(json_extract(evidence_json, '$.revenue') AS DOUBLE) < ?",
        [p.SMALL_REVENUE_USD],
    ).fetchone()[0]
    exempt = con.execute("SELECT method, category, n FROM single_bidder_exempt ORDER BY 1, 2").fetchall()
    excluded = _excluded_individuals(con, skipped)
    return {
        "SINGLE_BIDDER": {
            "excluded_by_design": [
                {"method": method, "category": category, "processes": n} for method, category, n in exempt
            ]
        },
        "SUPPLIER_NOT_ACTIVE": {"by_timing": {key: n for key, n in timing}}
        | excluded.get(d.SUPPLIER_NOT_ACTIVE, {}),
        "NEW_SUPPLIER": excluded.get(d.NEW_SUPPLIER, {}),
        "GHOST_COMPANY_LIST": excluded.get(d.GHOST_COMPANY_LIST, {}),
        "CONTRACT_VS_COMPANY_SIZE": {
            "fired_with_revenue_under_usd": p.SMALL_REVENUE_USD,
            "fired_with_revenue_under_threshold": low_revenue,
        },
    }


def _sql_list(codes: frozenset[str]) -> str:
    return "[" + ", ".join(quote_literal(c) for c in sorted(codes)) + "]"


def _write_parquet(con: duckdb.DuckDBPyConnection, query: str, target: Path) -> int:
    """Write a query to Parquet atomically (temp file, then rename) and return its row count."""
    tmp = target.with_suffix(".parquet.tmp")
    con.execute(f"COPY ({query}) TO {quote_literal(str(tmp))} (FORMAT PARQUET, COMPRESSION ZSTD)")
    os.replace(tmp, target)
    rows = con.execute(f"SELECT count(*) FROM read_parquet({quote_literal(str(target))})").fetchone()
    return rows[0]


def build_marts(lake_dir: Path, marts_dir: Path, *, now: datetime | None = None) -> dict[str, Any]:
    """Compute signals, scores and marts. Returns the build summary (also written as JSON)."""
    started = time.monotonic()
    available = set(existing_tables(lake_dir))
    absent_core = [t for t in CORE_TABLES if t not in available]
    if absent_core:
        raise LakeNotFoundError(f"Missing core lake tables in {lake_dir}: {', '.join(absent_core)}")
    marts_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = marts_dir / ".duckdb_tmp"
    con = connect_lake(lake_dir, temp_dir=tmp_dir)
    try:
        summary = _build(con, available, marts_dir, lake_dir)
    finally:
        con.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)
    summary["built_at"] = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    summary["duration_seconds"] = round(time.monotonic() - started, 1)
    (marts_dir / SUMMARY_NAME).write_bytes(orjson.dumps(summary, option=orjson.OPT_INDENT_2))
    return summary


def _build(
    con: duckdb.DuckDBPyConnection, available: set[str], marts_dir: Path, lake_dir: Path
) -> dict[str, Any]:
    lake_rows = _table_counts(con, sorted(available))
    for statement in (q.CREATE_BASE, q.CREATE_WINNERS, q.CREATE_THRESHOLDS, q.CREATE_SIGNAL_ROWS):
        _run(con, statement)
    _prepare_statistical(con)
    _run(
        con,
        q.SINGLE_BIDDER_EXEMPT,
        {
            "competitive": p.COMPETITIVE_GROUP,
            "min_group": p.MIN_GROUP_SIZE,
            "max_tenderers": p.SINGLE_BIDDER_TENDERERS,
            "by_design_share": p.SINGLE_BIDDER_BY_DESIGN_SHARE,
        },
    )
    skipped = _registry_skips(con, available)

    timings: dict[str, float] = {}
    for code, (sql, params) in _signal_statements().items():
        if code in skipped:
            continue
        t0 = time.monotonic()
        _run(con, sql, params)
        timings[code] = round(time.monotonic() - t0, 1)

    _run(con, q.CREATE_WEIGHTS)
    con.executemany("INSERT INTO weights VALUES (?, ?)", list(SIGNAL_WEIGHTS.items()))
    anomaly_report = compute_anomaly_scores(con)
    _run(con, q.PROCESS_SCORES, {"max_score": MAX_SCORE, "context_codes": sorted(d.CONTEXT_CODES)})
    _run(con, q.SUPPLIER_PROFILES)

    fired = dict(con.execute("SELECT signal_code, count(*) FROM signal_rows GROUP BY 1").fetchall())
    marts_rows = {
        "process_signals": _write_parquet(
            con,
            "SELECT *, CASE WHEN signal_code IN (SELECT unnest(" + _sql_list(d.CONTEXT_CODES) + "))"
            " THEN 'context' ELSE 'risk' END AS kind FROM signal_rows ORDER BY ocid, signal_code",
            marts_dir / "process_signals.parquet",
        ),
        "process_scores": _write_parquet(
            con,
            "SELECT * FROM process_scores ORDER BY risk_score DESC, ocid",
            marts_dir / "process_scores.parquet",
        ),
        "supplier_profiles": _write_parquet(
            con, "SELECT * FROM supplier_profiles ORDER BY ruc", marts_dir / "supplier_profiles.parquet"
        ),
    }
    return {
        "lake_dir": str(lake_dir),
        "lake_rows": lake_rows,
        "marts_rows": marts_rows,
        "signals": {
            s.code: {"kind": s.kind}
            | (
                {"status": "not_computed", "reason": skipped[s.code]}
                if s.code in skipped
                else {"status": "computed", "fired": int(fired.get(s.code, 0)), "seconds": timings[s.code]}
            )
            for s in SIGNALS
        },
        "signals_skipped": skipped,
        "signal_details": _signal_details(con, skipped),
        "thresholds": _threshold_rows(con),
        "registry_coverage": _registry_coverage(con, skipped),
        "anomaly": {
            "model": "IsolationForest",
            "random_state": p.ANOMALY_RANDOM_STATE,
            "n_estimators": p.ANOMALY_N_ESTIMATORS,
            "per_method": anomaly_report,
        },
        "weights": SIGNAL_WEIGHTS,
    }
