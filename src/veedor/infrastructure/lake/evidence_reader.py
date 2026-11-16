"""Assemble an `EvidencePack` for one process from the Parquet lake and the marts (DuckDB).

Optional tables (registries, marts) may be absent: the corresponding facts are ``None`` and the
dossier renders them as ``no disponible``. Natural persons are masked here, before anything
reaches the pack, using the shared masking rule.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from veedor.core.settings import get_settings
from veedor.domain.dossier import source_catalog as catalog
from veedor.domain.dossier.models import (
    ComparisonStats,
    EvidencePack,
    HistoryFacts,
    ProcessFacts,
    RegistryFacts,
    SignalFact,
    Source,
    WinnerFacts,
)
from veedor.domain.masking import NATURAL_PERSON, mask_party, mask_payload, safe_free_text

LAKE_TABLES = (
    "processes",
    "awards",
    "tenderers",
    "suppliers_sri",
    "ghost_companies",
    "companies_supercias",
    "company_financials",
)
MART_TABLES = ("process_signals", "process_scores")
REFERENCE_DATES = (
    ("first_award_date", "fecha de adjudicación"),
    ("date_signed", "fecha de firma"),
    ("tender_start", "inicio de ofertas"),
    ("release_date", "fecha de publicación"),
)


def _day(value: Any) -> str | None:
    return None if value in (None, "") else str(value)[:10]


# Day of an award: its own date, else the same fallback as the process reference date.
_AWARD_DAY_SQL = (
    "coalesce(substr(a.award_date, 1, 10), substr(p.first_award_date, 1, 10), substr(p.date_signed, 1, 10), "
    "substr(p.tender_start, 1, 10), substr(p.release_date, 1, 10))"
)


def _reference_date(raw: dict[str, Any]) -> tuple[str, str] | None:
    """(ISO day, Spanish name of the field) using the signals engine's fallback order."""
    for field, name in REFERENCE_DATES:
        day = _day(raw.get(field))
        if day:
            return day, name
    return None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


class EvidenceReader:
    def __init__(self, lake_dir: Path | None = None, marts_dir: Path | None = None) -> None:
        settings = get_settings()
        self.lake_dir = lake_dir or settings.lake_dir
        self.marts_dir = marts_dir or settings.marts_dir
        self._comparison_cache: dict[tuple[str | None, int | None], ComparisonStats] = {}

    # connection ---------------------------------------------------------------------------
    def _connect(self) -> tuple[duckdb.DuckDBPyConnection, set[str]]:
        con = duckdb.connect(":memory:")
        present: set[str] = set()
        for table, directory in [(t, self.lake_dir) for t in LAKE_TABLES] + [
            (t, self.marts_dir) for t in MART_TABLES
        ]:
            path = directory / f"{table}.parquet"
            if path.is_file():
                escaped = str(path).replace("'", "''")
                con.execute(f"CREATE VIEW \"{table}\" AS SELECT * FROM read_parquet('{escaped}')")
                present.add(table)
        self._lock_down(con)
        return con, present

    def _lock_down(self, con: duckdb.DuckDBPyConnection) -> None:
        """Same lock-down as the API's LakeReader: only the lake and marts stay readable.

        `allowed_directories` is set before `enable_external_access=false`; `lock_configuration`
        stops any later statement from undoing either setting. The connection is in memory and with
        external access off nothing can be written to disk either.
        """
        allowed = ", ".join(
            "'" + str(path.resolve()).replace("'", "''") + "'" for path in (self.lake_dir, self.marts_dir)
        )
        con.execute(f"SET allowed_directories=[{allowed}]")
        con.execute("SET enable_external_access=false")
        con.execute("SET lock_configuration=true")

    @staticmethod
    def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        cursor = con.execute(sql, params)
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    def _retrieved(self, table: str) -> str | None:
        for directory in (self.lake_dir, self.marts_dir):
            path = directory / f"{table}.parquet"
            if path.is_file():
                return datetime.fromtimestamp(path.stat().st_mtime, UTC).date().isoformat()
        return None

    # public ---------------------------------------------------------------------------------
    def load(self, ocid: str) -> EvidencePack | None:
        con, present = self._connect()
        try:
            if "processes" not in present:
                return None
            rows = self._rows(con, "SELECT * FROM processes WHERE ocid = ?", [ocid])
            if not rows:
                return None
            raw = rows[0]
            process = self._process(raw, self._person_names(con, present, ocid))
            sources = [catalog.sercop("SERCOP datos abiertos OCDS: procesos", ocid)]
            signals, signals_ok = self._signals(con, present, ocid)
            if signals_ok:
                sources.append(catalog.veedor_indicators(ocid, self._retrieved("process_signals")))
            winner = self._winner(con, present, ocid, raw, sources)
            history = self._history(con, present, raw, winner[1] if winner else None)
            return EvidencePack(
                process=process,
                signals_available=signals_ok,
                signals=signals,
                risk_score=self._risk_score(con, present, ocid),
                winner=winner[0] if winner else None,
                history=history,
                comparison=self._comparison(con, raw),
                sources=sources,
            )
        finally:
            con.close()

    # parts ----------------------------------------------------------------------------------
    def _person_names(self, con: duckdb.DuckDBPyConnection, present: set[str], ocid: str) -> list[str]:
        """Names of natural persons that took part in this process (winner and tenderers)."""
        names: list[str] = []
        for table in ("awards", "tenderers"):
            if table in present:
                rows = self._rows(
                    con, f"SELECT supplier_ruc, supplier_name FROM {table} WHERE ocid = ?", [ocid]
                )
                names += [
                    r["supplier_name"]
                    for r in rows
                    if r["supplier_name"]
                    and mask_party(r["supplier_ruc"], r["supplier_name"])[2] == NATURAL_PERSON
                ]
        return names

    def _process(self, raw: dict[str, Any], person_names: list[str]) -> ProcessFacts:
        budget, total = raw.get("budget"), raw.get("award_total")
        ratio = round(total / budget, 4) if budget and budget > 0 and total is not None else None
        buyer_ruc, buyer_name, _ = mask_party(raw.get("buyer_ruc"), raw.get("buyer_name"))
        n_tenderers = raw.get("n_tenderers")
        cpc_text, _ = safe_free_text(_clean(raw.get("main_cpc_description")), person_names)
        return ProcessFacts(
            ocid=raw["ocid"],
            process_code=raw.get("process_code"),
            year=raw.get("year"),
            buyer_ruc=buyer_ruc,
            buyer_name=buyer_name,
            buyer_region=_clean(raw.get("buyer_region")),
            buyer_locality=_clean(raw.get("buyer_locality")),
            method=_clean(raw.get("method")),
            method_group=raw.get("method_group"),
            category=raw.get("category"),
            status=raw.get("status"),
            budget=budget,
            award_total=total,
            award_budget_ratio=ratio,
            n_tenderers=None if n_tenderers is None else int(n_tenderers),
            n_awards=raw.get("n_awards"),
            tender_start=_day(raw.get("tender_start")),
            tender_end=_day(raw.get("tender_end")),
            first_award_date=_day(raw.get("first_award_date")),
            date_signed=_day(raw.get("date_signed")),
            main_cpc=raw.get("main_cpc"),
            n_enquiries=None if raw.get("n_enquiries") is None else int(raw["n_enquiries"]),
            main_cpc_description=cpc_text,
        )

    def _signals(
        self, con: duckdb.DuckDBPyConnection, present: set[str], ocid: str
    ) -> tuple[list[SignalFact], bool]:
        if "process_signals" not in present:
            return [], False
        from veedor.domain.signals import SIGNALS_BY_CODE

        out: list[SignalFact] = []
        for row in self._rows(con, "SELECT * FROM process_signals WHERE ocid = ?", [ocid]):
            code = row["signal_code"]
            evidence = json.loads(row["evidence_json"]) if row.get("evidence_json") else {}
            definition = SIGNALS_BY_CODE.get(code)
            out.append(
                SignalFact(
                    code=code,
                    label_es=definition.label_es if definition else code,
                    value=row.get("value"),
                    threshold=row.get("threshold"),
                    evidence=mask_payload(evidence) if isinstance(evidence, dict) else {},
                )
            )
        return out, True

    def _risk_score(self, con: duckdb.DuckDBPyConnection, present: set[str], ocid: str) -> float | None:
        if "process_scores" not in present:
            return None
        rows = self._rows(con, "SELECT risk_score FROM process_scores WHERE ocid = ?", [ocid])
        return rows[0]["risk_score"] if rows else None

    def _winner(
        self,
        con: duckdb.DuckDBPyConnection,
        present: set[str],
        ocid: str,
        raw: dict[str, Any],
        sources: list[Source],
    ) -> tuple[WinnerFacts, str | None] | None:
        if "awards" not in present:
            return None
        rows = self._rows(
            con,
            "SELECT supplier_ruc, any_value(supplier_name) AS supplier_name, sum(amount) AS total, "
            "min(award_date) AS first_date FROM awards WHERE ocid = ? AND supplier_ruc IS NOT NULL "
            "GROUP BY supplier_ruc ORDER BY total DESC NULLS LAST, supplier_ruc",
            [ocid],
        )
        if not rows:
            return None
        top = rows[0]
        real_ruc = top["supplier_ruc"]
        ruc, name, kind = mask_party(real_ruc, top["supplier_name"])
        if kind == "unknown":  # no usable RUC: the supplier is never named
            ruc, name = None, None
        sources.append(catalog.sercop("SERCOP datos abiertos OCDS: adjudicaciones", ocid))
        registry = self._registry(con, present, real_ruc, kind == NATURAL_PERSON, ruc, raw, sources)
        winner = WinnerFacts(ruc=ruc, name=name, kind=kind, n_award_suppliers=len(rows), registry=registry)
        return winner, real_ruc

    def _registry(
        self,
        con: duckdb.DuckDBPyConnection,
        present: set[str],
        real_ruc: str | None,
        natural: bool,
        shown_ruc: str | None,
        raw: dict[str, Any],
        sources: list[Source],
    ) -> RegistryFacts:
        facts: dict[str, Any] = {}
        if not real_ruc:
            return RegistryFacts()
        if "suppliers_sri" in present:
            rows = self._rows(con, "SELECT * FROM suppliers_sri WHERE ruc = ? LIMIT 1", [real_ruc])
            if rows:
                r = rows[0]
                facts.update(
                    status=_clean(r.get("status")),
                    taxpayer_type=_clean(r.get("taxpayer_type")),
                    activity_start_date=_day(r.get("activity_start_date")),
                    suspension_date=_day(r.get("suspension_date")),
                    restart_date=_day(r.get("restart_date")),
                    ciiu_code=_clean(r.get("ciiu_code")),
                    activity=safe_free_text(_clean(r.get("activity")))[0],
                    province=_clean(r.get("province")),
                    legal_name=None if natural else _clean(r.get("legal_name")),
                )
                sources.append(catalog.sri("SRI: registro de contribuyentes", shown_ruc))
        if "ghost_companies" in present:
            hit = self._rows(con, "SELECT 1 AS hit FROM ghost_companies WHERE ruc = ? LIMIT 1", [real_ruc])
            facts["ghost_listed"] = bool(hit)
            sources.append(catalog.sri("SRI: listado de empresas fantasmas", shown_ruc))
        if "companies_supercias" in present:
            rows = self._rows(
                con, "SELECT company_type FROM companies_supercias WHERE ruc = ? LIMIT 1", [real_ruc]
            )
            if rows:
                facts["company_type"] = _clean(rows[0].get("company_type"))
                sources.append(catalog.supercias("Superintendencia de Compañías: directorio", shown_ruc))
        if "company_financials" in present:
            rows = self._rows(
                con,
                "SELECT year, revenue FROM company_financials WHERE ruc = ? AND revenue IS NOT NULL "
                "ORDER BY year DESC",
                [real_ruc],
            )
            if rows:
                facts.update(latest_revenue=rows[0]["revenue"], latest_revenue_year=rows[0]["year"])
                reference = _reference_date(raw)
                award_year = int(reference[0][:4]) if reference else raw.get("year")
                facts["award_year"] = award_year
                same_year = [r["revenue"] for r in rows if r["year"] == award_year]
                facts["revenue_award_year"] = same_year[0] if same_year else None
                sources.append(catalog.supercias("Superintendencia de Compañías: ingresos", shown_ruc))
        return RegistryFacts(**facts)

    def _history(
        self,
        con: duckdb.DuckDBPyConnection,
        present: set[str],
        raw: dict[str, Any],
        supplier_ruc: str | None,
    ) -> HistoryFacts | None:
        reference = _reference_date(raw)
        buyer_ruc = raw.get("buyer_ruc")
        if "awards" not in present or not (supplier_ruc and buyer_ruc and reference):
            return None
        rows = self._rows(
            con,
            f"WITH pair AS (SELECT a.ocid, a.amount, {_AWARD_DAY_SQL} AS day, p.year AS process_year "
            "FROM awards a JOIN processes p USING (ocid) WHERE a.supplier_ruc = ? AND p.buyer_ruc = ?) "
            "SELECT count(*) FILTER (WHERE ocid <> ? AND day < ?) AS n, "
            "count(amount) FILTER (WHERE ocid <> ? AND day < ?) AS n_amount, "
            "sum(amount) FILTER (WHERE ocid <> ? AND day < ?) AS total, "
            "min(day) FILTER (WHERE ocid <> ? AND day < ?) AS first_day, "
            "max(day) FILTER (WHERE ocid <> ? AND day < ?) AS last_day, "
            "count(*) AS n_pair, "
            "min(coalesce(CAST(substr(day, 1, 4) AS INTEGER), process_year)) AS first_year, "
            "max(coalesce(CAST(substr(day, 1, 4) AS INTEGER), process_year)) AS last_year FROM pair",
            [supplier_ruc, buyer_ruc, *([raw["ocid"], reference[0]] * 5)],
        )
        r = rows[0]
        return HistoryFacts(
            reference_date=reference[0],
            reference_date_kind=reference[1],
            n_previous_awards=int(r["n"]),
            n_with_amount=int(r["n_amount"]),
            total_previous_amount=r["total"],
            first_award_date=r["first_day"],
            last_award_date=r["last_day"],
            n_pair_awards=int(r["n_pair"]),
            pair_first_year=r["first_year"],
            pair_last_year=r["last_year"],
        )

    def _comparison(self, con: duckdb.DuckDBPyConnection, raw: dict[str, Any]) -> ComparisonStats | None:
        method, year = _clean(raw.get("method")), raw.get("year")
        if method is None or year is None:
            return None
        key = (method, year)
        if key not in self._comparison_cache:
            r = self._rows(
                con,
                "SELECT count(*) AS n, median(n_tenderers) AS med_t, "
                "avg(CASE WHEN n_tenderers = 1 THEN 1.0 ELSE 0.0 END) FILTER (WHERE n_tenderers IS NOT NULL) "
                "AS single_share, "
                "median(award_total / budget) FILTER (WHERE budget > 0 AND award_total IS NOT NULL) "
                "AS med_ratio "
                "FROM processes WHERE method = ? AND year = ?",
                [method, year],
            )[0]
            self._comparison_cache[key] = ComparisonStats(
                method=method,
                year=year,
                n_processes=int(r["n"]),
                median_tenderers=r["med_t"],
                single_bidder_share=None if r["single_share"] is None else round(r["single_share"], 4),
                median_award_budget_ratio=None if r["med_ratio"] is None else round(r["med_ratio"], 4),
            )
        return self._comparison_cache[key]
