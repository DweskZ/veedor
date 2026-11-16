"""Generated artefacts must not identify suppliers or buyers (names or 13-digit RUCs)."""

from __future__ import annotations

import re

import duckdb
import orjson
import pytest

from veedor.evaluation import backtest, coverage, history, report

RUC = re.compile(r"\b\d{13}\b")


@pytest.fixture(scope="module")
def artefacts(synthetic_dirs, tmp_path_factory) -> str:
    """Everything the harness writes, concatenated: JSON, CSVs and the rendered document."""
    out = tmp_path_factory.mktemp("artefacts")
    bt = backtest.run_backtest(*synthetic_dirs, n_boot=100, seed=1)
    bt["history"] = [history.entry_from(bt, "synthetic run")]
    cov = coverage.run_coverage(*synthetic_dirs)
    report.write_csvs(bt, out)
    report.write_coverage_csvs(cov, out)
    texts = [
        orjson.dumps(bt, option=orjson.OPT_SERIALIZE_NUMPY).decode(),
        orjson.dumps(cov, option=orjson.OPT_SERIALIZE_NUMPY).decode(),
        report.render(bt, cov),
        report.summary_text(bt),
        *(p.read_text(encoding="utf-8") for p in out.glob("*.csv")),
    ]
    return "\n".join(texts)


def test_no_thirteen_digit_numbers(artefacts):
    assert RUC.findall(artefacts) == []


def test_no_supplier_or_buyer_names_or_rucs(artefacts, synthetic_dirs):
    _, marts = synthetic_dirs
    rows = (
        duckdb.connect()
        .execute(
            f"SELECT DISTINCT winner_name, winner_ruc, buyer_name, buyer_ruc "
            f"FROM read_parquet('{marts / 'process_scores.parquet'}')"
        )
        .fetchall()
    )
    identifiers = {value for row in rows for value in row if value}
    assert len(identifiers) > 40  # the fixture really has many names to look for
    leaked = sorted(i for i in identifiers if i in artefacts)
    assert leaked == []


def test_buyers_are_anonymised_by_rank(artefacts):
    assert "Buyer 01" in artefacts and "Buyer 02" in artefacts
