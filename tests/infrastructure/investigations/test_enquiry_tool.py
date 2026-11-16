# ruff: noqa: E501
"""The `process_texts` tool over synthetic texts: counts and dates only, nothing else leaves it."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from veedor.domain.investigation.enquiry_topics import TOPIC_DESCRIPTIONS_ES
from veedor.domain.investigation.results import EnquirySummary
from veedor.infrastructure.investigations.enquiries import EnquiryTool
from veedor.infrastructure.vectors.embedding import FakeEmbedder

OCID = "ocds-5wno2w-ENQ-1"
SCHEMA = pa.schema([("ocid", pa.string()), ("kind", pa.string()), ("seq", pa.int32()), ("date", pa.string()), ("text", pa.string())])
Q, A = "enquiry_question", "enquiry_answer"
SECRET = "zafiro-secreto"


def row(kind, seq, day, text):
    return {"ocid": OCID, "kind": kind, "seq": seq, "date": f"{day}T00:00:00-05:00" if day else None, "text": text}


@pytest.fixture
def texts_dir(tmp_path: Path) -> Path:
    rows = [
        row(Q, 0, "2023-05-01", f"{TOPIC_DESCRIPTIONS_ES['deadlines']} {SECRET}"),  # near the deadlines topic
        row(A, 0, "2023-05-03", "Se acepta la ampliación"),
        row(Q, 1, "2023-05-29", TOPIC_DESCRIPTIONS_ES["price"]),
        row(A, 1, "2023-06-05", "Respuesta sobre el precio"),
        row(Q, 2, "2023-05-31", "zorro quimera lámpara nube sauce"),  # no topic, no answer
        row(Q, 3, None, TOPIC_DESCRIPTIONS_ES["requirements"]),  # no date
        row(A, 3, "2023-06-02", "Requisitos aclarados"),
        row("award_text", 0, "2023-06-10", "ignorado"),
    ]
    other = {**row(Q, 0, "2023-05-01", "otra pregunta"), "ocid": "ocds-5wno2w-OTHER"}
    pq.write_table(pa.Table.from_pylist([*rows, other], schema=SCHEMA), tmp_path / "process_texts.parquet")
    return tmp_path


def tool(texts_dir: Path, floor: float = 0.6) -> EnquiryTool:
    return EnquiryTool(texts_dir, FakeEmbedder(), floor)


def args(deadline="2023-06-01", late=3):
    return {"ocid": OCID, "deadline_day": deadline, "late_days": late}


def test_counts_dates_and_topics_by_code(texts_dir):
    result = tool(texts_dir).process_texts(args())
    summary = EnquirySummary.model_validate(result)
    assert summary.n_with_text == 4 and summary.n_answered == 3
    assert summary.n_dated_pairs == 2 and summary.median_days_to_answer == 4.5 and summary.max_days_to_answer == 7
    assert summary.n_late == 2  # 29 and 31 May are within 3 days of 1 June; 1 May is not
    assert (summary.topic_deadlines, summary.topic_price, summary.topic_requirements, summary.topic_specifications) == (1, 1, 1, 0)


def test_without_a_deadline_the_late_count_is_unknown_not_zero(texts_dir):
    assert tool(texts_dir).process_texts(args(deadline=None))["n_late"] is None


def test_the_result_holds_numbers_only(texts_dir):
    result = tool(texts_dir).process_texts(args())
    assert SECRET not in repr(result)
    assert all(v is None or isinstance(v, int | float) for v in result.values())


def test_a_process_with_no_texts_gives_zeros(texts_dir):
    result = tool(texts_dir).process_texts({"ocid": "ocds-5wno2w-NONE", "deadline_day": None, "late_days": 3})
    assert result["n_with_text"] == 0 and result["n_dated_pairs"] == 0 and result["median_days_to_answer"] is None


@pytest.mark.parametrize("bad", [{"ocid": "x' OR 1=1 --", "deadline_day": None, "late_days": 3}, {"ocid": OCID, "deadline_day": None, "late_days": "3"}, {}])
def test_the_arguments_are_validated_before_any_query(texts_dir, bad):
    with pytest.raises(ValueError):
        tool(texts_dir).process_texts(bad)


def test_a_missing_table_is_an_error_not_an_invented_zero(tmp_path):
    with pytest.raises(FileNotFoundError):
        tool(tmp_path).process_texts(args())


def test_the_reader_cannot_leave_the_texts_folder(texts_dir):
    t = tool(texts_dir)
    t.process_texts(args())
    import duckdb

    with pytest.raises(duckdb.Error):
        t._connection().execute("SELECT * FROM read_text('/etc/hosts')").fetchall()
