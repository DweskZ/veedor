"""Extraction of enquiry and award texts from synthetic OCDS releases (no real data)."""

from __future__ import annotations

import gzip
from pathlib import Path

import orjson
import pyarrow.parquet as pq

from veedor.infrastructure.ocds.flatten import build_lake
from veedor.infrastructure.ocds.texts import (
    MAX_TEXT_CHARS,
    TEXT_SCHEMA,
    build_texts,
    cap_text,
    clean_text,
    drop_reason,
    extract_texts,
)

COMPANY_AUTHOR = {"id": "EC-RUC-1790012345001-1", "name": "Constructora Ejemplo S.A."}
PERSON_AUTHOR = {"id": "EC-RUC-1712345678001-2", "name": "Maria Ficticia Quispe"}


def release(enquiries=None, awards=None, ocid="ocds-5wno2w-TEST-1"):
    return {
        "ocid": ocid,
        "date": "2023-01-01T00:00:00-05:00",
        "tender": {"id": "TEST-1", "enquiries": enquiries or []},
        "awards": awards or [],
    }


def enquiry(question, answer=None, author=COMPANY_AUTHOR, **extra):
    row = {"id": "1", "date": "2023-01-02T00:00:00-05:00", "description": question, "author": author}
    if answer is not None:
        row |= {"answer": answer, "dateAnswered": "2023-01-03T00:00:00-05:00"}
    return row | extra


def test_question_answer_and_award_text_become_rows_with_their_ocds_path():
    rows, drops = extract_texts(
        release(
            [enquiry("¿Se amplía el plazo de entrega?", "Se amplía hasta el 10 de mayo.")],
            [
                {
                    "id": 1,
                    "date": "2023-02-01T00:00:00-05:00",
                    "description": "Cumple con los pliegos y la oferta.",
                }
            ],
        )
    )
    assert not drops
    by_kind = {r["kind"]: r for r in rows}
    assert set(by_kind) == {"enquiry_question", "enquiry_answer", "award_text"}
    q, a, w = by_kind["enquiry_question"], by_kind["enquiry_answer"], by_kind["award_text"]
    assert (q["source_field"], q["author_kind"], q["date"]) == (
        "tender.enquiries[0].description", "oferente", "2023-01-02T00:00:00-05:00",
    )  # fmt: skip
    assert (a["source_field"], a["author_kind"], a["date"]) == (
        "tender.enquiries[0].answer", "entidad", "2023-01-03T00:00:00-05:00",
    )  # fmt: skip
    assert (w["source_field"], w["author_kind"], w["seq"]) == ("awards[0].description", "entidad", 0)


def test_source_field_index_follows_the_position_in_the_list():
    rows, _ = extract_texts(
        release([enquiry("primera pregunta aquí"), "no es un dict", enquiry("tercera pregunta aquí")])
    )
    assert [(r["seq"], r["source_field"]) for r in rows] == [
        (0, "tender.enquiries[0].description"),
        (2, "tender.enquiries[2].description"),
    ]


def test_no_author_name_or_ruc_is_stored_only_a_person_flag():
    rows, _ = extract_texts(
        release(
            [enquiry("pregunta de una persona", author=PERSON_AUTHOR), enquiry("pregunta de una sociedad")]
        )
    )
    assert [r["author_person"] for r in rows] == [True, False]
    assert set(rows[0]) == set(TEXT_SCHEMA.names)
    assert "Quispe" not in repr(rows) and "1712345678001" not in repr(rows)


def test_whitespace_is_collapsed_and_control_characters_removed():
    assert clean_text("  uno\n\n dos\t\ttres\x00 cuatro ") == "uno dos tres cuatro"
    assert clean_text(None) == "" and clean_text(5) == ""


def test_empty_and_symbol_only_texts_are_dropped_and_counted():
    rows, drops = extract_texts(release([enquiry("   ", ""), enquiry("---", "...."), enquiry(None, None)]))
    assert rows == []
    assert drops["enquiry_question:empty"] == 1 and drops["enquiry_question:no_letters"] == 1
    assert drops["enquiry_answer:empty"] == 1 and drops["enquiry_answer:no_letters"] == 1


def test_boilerplate_only_texts_are_dropped():
    for text in (
        "Aclaración",
        "SI",
        "No aplica",
        "Ver acta",
        "Se adjunta lo solicitado",
        "Revisar acta adjunta",
    ):
        assert drop_reason(clean_text(text)) == "boilerplate", text
    for text in (
        "Se solicita ampliar el plazo de entrega por diez días",
        "Cumple con lo solicitado en los pliegos",  # award text: kept on purpose
        "Ver acta 2023",  # has a number: not a bare pointer
    ):
        assert drop_reason(clean_text(text)) is None, text


def test_exact_duplicates_inside_one_process_are_dropped_across_case_and_accents():
    rows, drops = extract_texts(
        release(
            [enquiry("¿Cuál es el plazo?", "Treinta días."), enquiry("¿CUAL ES EL PLAZO?", "treinta dias")]
        )
    )
    assert [r["text"] for r in rows] == ["¿Cuál es el plazo?", "Treinta días."]
    assert drops["enquiry_question:duplicate"] == 1 and drops["enquiry_answer:duplicate"] == 1


def test_the_same_text_in_two_processes_is_kept_in_both():
    a, _ = extract_texts(release([enquiry("¿Cuál es el plazo?")], ocid="ocds-5wno2w-A"))
    b, _ = extract_texts(release([enquiry("¿Cuál es el plazo?")], ocid="ocds-5wno2w-B"))
    assert len(a) == len(b) == 1


def test_a_very_long_text_is_cut_at_a_word_boundary_and_flagged():
    long = ("palabra " * 600).strip()
    rows, _ = extract_texts(release([enquiry(long)]))
    assert rows[0]["truncated"] is True
    assert len(rows[0]["text"]) <= MAX_TEXT_CHARS and not rows[0]["text"].endswith(" ")
    assert rows[0]["text"].split(" ")[-1] == "palabra"  # no half word


def test_a_text_at_the_limit_is_kept_whole():
    text = "a" * MAX_TEXT_CHARS
    assert cap_text(text) == (text, False)
    assert cap_text(text + "b")[1] is True


def test_a_release_without_ocid_or_with_odd_shapes_yields_nothing_and_does_not_raise():
    assert extract_texts({"tender": {"enquiries": [enquiry("hola mundo cruel")]}}) == (
        [],
        extract_texts({})[1],
    )
    assert extract_texts({"ocid": "x", "tender": None, "awards": "no"})[0] == []
    assert extract_texts({"ocid": "x", "tender": {"enquiries": "no"}, "awards": [None, 3]})[0] == []


def _write_bulk(path: Path, releases: list[dict]) -> None:
    with gzip.open(path, "wb") as handle:
        for item in releases:
            handle.write(orjson.dumps(item) + b"\n")


def test_build_texts_writes_the_parquet_and_the_counts(tmp_path: Path):
    bulk = tmp_path / "bulk.jsonl.gz"
    _write_bulk(
        bulk,
        [
            release([enquiry("¿Cuál es el plazo de entrega?", "Treinta días.")], ocid="ocds-5wno2w-A"),
            release([enquiry("Aclaración")], ocid="ocds-5wno2w-B"),
        ],
    )
    summary = build_texts(bulk, tmp_path / "texts")
    table = pq.read_table(tmp_path / "texts" / "process_texts.parquet")
    assert table.schema.equals(TEXT_SCHEMA)
    assert table.num_rows == summary["rows"] == 2
    assert summary["processes_with_text"] == 1 and summary["releases"] == 2
    assert summary["dropped"] == {"enquiry_question:boilerplate": 1}
    assert not (tmp_path / "texts" / "process_texts.parquet.tmp").exists()


def test_lake_build_can_write_the_texts_in_the_same_pass(tmp_path: Path):
    bulk = tmp_path / "bulk.jsonl.gz"
    _write_bulk(bulk, [release([enquiry("¿Cuál es el plazo de entrega?")])])
    without = build_lake(bulk, tmp_path / "data" / "lake")
    assert "texts" not in without and not (tmp_path / "data" / "texts").exists()
    with_texts = build_lake(bulk, tmp_path / "data" / "lake", with_texts=True)
    assert with_texts["texts"] == 1
    assert (
        tmp_path / "data" / "texts" / "process_texts.parquet"
    ).is_file()  # next to the lake, not inside it
    assert not (tmp_path / "data" / "lake" / "process_texts.parquet").exists()
