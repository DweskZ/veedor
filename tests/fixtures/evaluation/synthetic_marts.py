"""Tiny synthetic lake and marts for the evaluation tests (no real data, no network)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pyarrow as pa

COMPETITIVE = "Subasta Inversa Electrónica"
CATALOGUE = "Catálogo electrónico - synthetic convention"
GHOST_SIGNALS = ("GHOST_COMPANY_LIST", "SUPPLIER_NOT_ACTIVE")

# (ruc, notification date). 09920000xx001 are companies (third digit 9); 0912345678001 is a natural person.
DEFAULT_BUYER = ("1760000000001", "Municipality of Testville")
OTHER_BUYER = ("1799999999001", "Alpha Regional Council")
POSITIVES = {
    "0992000001001": "2019-01-01",  # all awards before notification
    "0992000002001": "2019-01-01",  # one award before, one after
    "0992000003001": "2017-01-01",  # all awards after notification
    "0992000004001": None,  # no notification date
    "0912345678001": "2019-01-01",  # natural person
}


def _kind(ruc: str) -> str:
    return {"9": "company"}.get(ruc[2], "natural_person")


def build(lake: Path, marts: Path) -> dict[str, int]:
    """Write the five Parquet tables the evaluation reads; return a few counts for assertions."""
    lake.mkdir(parents=True, exist_ok=True)
    marts.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    def add(
        ruc,
        name,
        date,
        signals,
        method=COMPETITIVE,
        group="competitive",
        amount=1000.0,
        context=(),
        buyer=DEFAULT_BUYER,
    ):
        listed = ["GHOST_COMPANY_LISTED_LATER"] if "GHOST_COMPANY_LIST" in signals else []
        rows.append(
            {
                "ocid": f"oc-{len(rows):04d}",
                "ruc": ruc,
                "name": name,
                "date": date,
                "signals": list(signals),
                "context": [*listed, *context],
                "method": method,
                "mgroup": group,
                "amount": amount,
                "buyer_ruc": buyer[0],
                "buyer_name": buyer[1],
            }
        )

    for i in range(40):  # unlabelled companies: 3 processes each, some single-bidder
        ruc = f"09930000{i:02d}001"
        for k in range(3):
            single = i % 4 == 0 and k == 0
            same_year = ["CONTRACT_VS_COMPANY_SIZE_SAME_YEAR"] if (i, k) == (1, 0) else []
            add(
                ruc,
                f"UNLABELLED {i}",
                f"2018-0{k + 1}-10",
                ["SINGLE_BIDDER"] if single else [],
                context=same_year,
                buyer=OTHER_BUYER if i % 2 else DEFAULT_BUYER,
            )
    for i in range(5):  # unlabelled natural persons
        add(f"09{i + 1}0000000001", f"PERSON {i}", "2018-05-05", [])
    add("0992000001001", "POSITIVE ONE", "2018-02-01", [*GHOST_SIGNALS, "SINGLE_BIDDER"])
    add("0992000001001", "POSITIVE ONE", "2018-03-01", list(GHOST_SIGNALS))
    add("0992000002001", "POSITIVE TWO", "2018-04-01", list(GHOST_SIGNALS))
    add("0992000002001", "POSITIVE TWO", "2020-04-01", [*GHOST_SIGNALS, "SINGLE_BIDDER"])
    add("0992000003001", "POSITIVE THREE", "2018-06-01", list(GHOST_SIGNALS))
    add(
        "0992000004001",
        "POSITIVE FOUR",
        "2018-07-01",
        [*GHOST_SIGNALS, "CONTRACT_VS_COMPANY_SIZE"],
        buyer=OTHER_BUYER,
    )
    add("0912345678001", "POSITIVE NATURAL", "2018-08-01", list(GHOST_SIGNALS))
    add("0992000001001", "POSITIVE ONE", "2018-09-01", [], CATALOGUE, "catalogue")

    con = duckdb.connect()
    con.register("rows_view", pa.Table.from_pylist(rows))
    con.execute(
        f"""
        COPY (SELECT ocid, mgroup AS method_group, date || 'T00:00:00-05:00' AS first_award_date,
                     NULL::VARCHAR AS date_signed, NULL::VARCHAR AS release_date
              FROM rows_view) TO '{lake / "processes.parquet"}' (FORMAT PARQUET)
        """
    )
    con.execute(
        f"""
        COPY (SELECT ocid, 0.0 AS risk_score, signals AS signal_codes,
                     len(context)::INTEGER AS n_context_signals, context AS context_signal_codes,
                     CASE WHEN mgroup = 'competitive'
                          THEN (len(ocid) + ascii(ocid[-1]) % 7) / 10.0 END AS anomaly_score,
                     amount AS award_total, year(date::DATE)::SMALLINT AS year, buyer_ruc,
                     buyer_name, method, ruc AS winner_ruc, name AS winner_name,
                     CASE substr(ruc, 3, 1) WHEN '9' THEN 'company' ELSE 'natural_person' END AS winner_kind
              FROM rows_view) TO '{marts / "process_scores.parquet"}' (FORMAT PARQUET)
        """
    )
    con.execute(
        f"""
        COPY (SELECT ocid, signal AS signal_code, 1.0 AS value, 1.0 AS threshold, '{{}}' AS evidence_json,
                     kind
              FROM (SELECT ocid, unnest(signals) AS signal, 'risk' AS kind FROM rows_view
                    UNION ALL
                    SELECT ocid, unnest(context) AS signal, 'context' AS kind FROM rows_view)
              ) TO '{marts / "process_signals.parquet"}' (FORMAT PARQUET)
        """
    )
    ghost = [(r, d) for r, d in POSITIVES.items()]
    con.execute("CREATE TABLE g(ruc VARCHAR, notification_date VARCHAR)")
    con.executemany("INSERT INTO g VALUES (?, ?)", ghost)
    con.execute(f"COPY g TO '{lake / 'ghost_companies.parquet'}' (FORMAT PARQUET)")
    con.execute("CREATE TABLE f(ruc VARCHAR, year INTEGER, revenue DOUBLE)")
    con.execute("INSERT INTO f VALUES ('0993000000001', 2017, 500.0)")
    con.execute(f"COPY f TO '{lake / 'company_financials.parquet'}' (FORMAT PARQUET)")
    return {"n_processes": len(rows)}
