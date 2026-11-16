"""Quote selection: pairs, similarity floor, near-duplicates, exclusions and the end-to-end build."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from veedor.domain.quotes.topics import SIGNAL_TOPICS_ES
from veedor.infrastructure.ocds.texts import TEXT_SCHEMA
from veedor.infrastructure.quotes.source import LakeQuoteSource, MissingInputError
from veedor.infrastructure.quotes.store import QUOTES_SCHEMA, STATS_SCHEMA, ParquetQuoteSink
from veedor.infrastructure.vectors.embedding import FakeEmbedder
from veedor.use_cases.build_quotes import (
    MAX_QUOTES,
    ProcessBundle,
    TextRow,
    build_quotes,
    judge_texts,
    name_context,
    select_for_process,
    shorten,
    topic_vectors,
)

OCID = "ocds-5wno2w-Q-1"
PERSON = "Pedro Mora Lopez"
COMPANY = "Constructora Ejemplo S.A."
# Words of the SHORT_TENDER_WINDOW topic: the hashed fake embedder ranks passages by shared words.
ON_TOPIC = "plazos prórrogas fecha límite ofertas ampliación cronograma"
OFF_TOPIC = "zorro quimera lámpara nube sauce"
FLOOR = 0.2


def row(kind, seq, text, **kw):
    base = dict(
        kind=kind,
        seq=seq,
        text=text,
        date="2023-01-02",
        author_kind="oferente" if kind == "enquiry_question" else "entidad",
        source_field=f"tender.enquiries[{seq}].{'description' if kind == 'enquiry_question' else 'answer'}",
        truncated=False,
        author_person=False,
    )
    return TextRow(**(base | kw))


def bundle(texts, signals=("SHORT_TENDER_WINDOW",), persons=(PERSON,), protected=(COMPANY,)):
    return ProcessBundle(OCID, tuple(signals), tuple(texts), tuple(persons), tuple(protected))


@pytest.fixture(scope="module")
def topics():
    return topic_vectors(FakeEmbedder())


def select(b, topics, floor=FLOOR):
    embedder = FakeEmbedder()
    judged = judge_texts(b)
    texts = sorted({j.row.text[:1000] for j in judged if j.verdict.eligible})
    vectors = dict(zip(texts, embedder.embed(texts), strict=True)) if texts else {}
    codes, matrix = topics
    return select_for_process(b, judged, vectors, codes, matrix, floor)


def test_topics_cover_every_signal_code(topics):
    assert set(topics[0]) == set(SIGNAL_TOPICS_ES)


def test_a_question_is_shown_with_its_eligible_answer_as_a_pair(topics):
    b = bundle(
        [
            row("enquiry_question", 0, f"¿{ON_TOPIC}?"),
            row("enquiry_answer", 0, "Se amplía el plazo cinco días."),
        ]
    )
    result = select(b, topics)
    assert len(result.quotes) == 1
    quote = result.quotes[0]
    assert quote["kind"] == "enquiry_question" and quote["pair_kind"] == "enquiry_answer"
    assert quote["pair_text"] == "Se amplía el plazo cinco días."
    assert quote["pair_source_field"] == "tender.enquiries[0].answer"
    assert quote["related_signal"] == "SHORT_TENDER_WINDOW" and quote["similarity"] >= FLOOR


def test_an_unsafe_answer_is_not_paired_but_the_question_still_shows(topics):
    b = bundle(
        [
            row("enquiry_question", 0, f"¿{ON_TOPIC}?"),
            row("enquiry_answer", 0, "Se concluye que hubo fraude."),
        ]
    )
    quote = select(b, topics).quotes[0]
    assert quote["pair_text"] is None and quote["pair_kind"] is None


def test_an_answer_is_withheld_when_its_question_is_withheld(topics):
    b = bundle(
        [
            row("enquiry_question", 0, f"{ON_TOPIC} escriba a juan@correo.com"),
            row("enquiry_answer", 0, f"{ON_TOPIC} respuesta"),
        ]
    )
    result = select(b, topics)
    assert result.quotes == []
    assert result.stats["excluded_personal"] == 2 and result.stats["n_eligible"] == 0
    assert result.reasons["personal:question_excluded"] == 1


def test_an_exchange_asked_by_a_natural_person_is_withheld_whole(topics):
    b = bundle(
        [
            row("enquiry_question", 0, f"¿{ON_TOPIC}?", author_person=True),
            row("enquiry_answer", 0, f"{ON_TOPIC} respuesta", author_person=True),
        ]
    )
    assert select(b, topics).quotes == []


def test_an_answer_without_a_stored_question_is_shown_alone(topics):
    quote = select(bundle([row("enquiry_answer", 3, f"{ON_TOPIC} respuesta")]), topics).quotes[0]
    assert quote["kind"] == "enquiry_answer" and quote["pair_text"] is None


def test_award_text_is_a_quote_of_its_own(topics):
    award = row(
        "award_text",
        0,
        f"Adjudicado: {ON_TOPIC}",
        author_kind="entidad",
        source_field="awards[0].description",
    )
    quote = select(bundle([award]), topics).quotes[0]
    assert (quote["kind"], quote["source_field"], quote["pair_text"]) == (
        "award_text",
        "awards[0].description",
        None,
    )


def test_passages_under_the_similarity_floor_are_not_shown_and_are_counted(topics):
    b = bundle([row("enquiry_question", 0, OFF_TOPIC), row("enquiry_question", 1, f"{ON_TOPIC}?")])
    result = select(b, topics)
    assert [q["source_field"] for q in result.quotes] == ["tender.enquiries[1].description"]
    assert result.stats["below_floor"] == 1 and result.stats["n_eligible"] == 2


def test_only_the_topics_of_the_fired_signals_are_used(topics):
    on_topic_for_other_signal = "adjudicación proveedor contrataciones anteriores varios contratos"
    b = bundle([row("enquiry_question", 0, on_topic_for_other_signal)], signals=("SHORT_TENDER_WINDOW",))
    assert select(b, topics).quotes == []
    b = bundle([row("enquiry_question", 0, on_topic_for_other_signal)], signals=("BUYER_CONCENTRATION",))
    assert select(b, topics).quotes[0]["related_signal"] == "BUYER_CONCENTRATION"


def test_a_process_whose_signals_have_no_topic_shows_nothing_and_counts_below_floor(topics):
    result = select(bundle([row("enquiry_question", 0, ON_TOPIC)], signals=("UNKNOWN_CODE",)), topics)
    assert result.quotes == [] and result.stats["below_floor"] == 1


def test_at_most_three_quotes_and_near_duplicates_are_skipped(topics):
    distinct = [
        "plazos prórrogas fecha límite",
        "ampliación cronograma ofertas días",
        "preguntas respuestas plazos cierre",
        "fecha cierre prórrogas ampliación",
        "días cronograma preguntas límite",
    ]
    result = select(bundle([row("enquiry_question", i, t) for i, t in enumerate(distinct)]), topics)
    assert len(result.quotes) == MAX_QUOTES == 3
    assert [q["rank"] for q in result.quotes] == [1, 2, 3]
    sims = [q["similarity"] for q in result.quotes]
    assert sims == sorted(sims, reverse=True) or any(q["pair_text"] for q in result.quotes)
    twins = [
        row("enquiry_question", 0, "plazos prórrogas fecha límite"),
        row("enquiry_question", 1, "plazos prórrogas fecha límite."),
    ]
    out = select(bundle(twins), topics)
    assert len(out.quotes) == 1 and out.near_duplicates == 1


def test_known_person_names_and_honorifics_never_reach_the_quotes(topics):
    b = bundle(
        [
            row("enquiry_question", 0, f"{ON_TOPIC} {PERSON}"),
            row("enquiry_question", 1, f"{ON_TOPIC} con el ing. juan perez"),
            row("enquiry_question", 2, f"{ON_TOPIC} de {COMPANY}"),
        ]
    )
    result = select(b, topics)
    assert [q["source_field"] for q in result.quotes] == [
        "tender.enquiries[2].description"
    ]  # the company passes
    assert COMPANY in result.quotes[0]["text"]
    assert result.stats["excluded_personal"] == 2 and result.stats["available_total"] == 3


def test_stats_arithmetic(topics):
    b = bundle(
        [
            row("enquiry_question", 0, f"{ON_TOPIC}?"),
            row("enquiry_question", 1, OFF_TOPIC),
            row("enquiry_question", 2, "hubo fraude"),
            row("enquiry_question", 3, "llame al 0991234567"),
        ]
    )
    s = select(b, topics).stats
    assert s["available_total"] == 4
    assert s["excluded_unsafe"] == 1 and s["excluded_personal"] == 1
    assert s["n_eligible"] == 2 and s["below_floor"] == 1 and s["n_quotes"] == 1


def test_shorten_cuts_at_a_word_and_says_so():
    assert shorten("corto") == ("corto", False)
    text, cut = shorten("palabra " * 200, 100)
    assert cut and text.endswith("…") and len(text) <= 101 and "palabr…" not in text


def test_name_context_masks_persons_and_protects_companies_and_buyers():
    parties = [
        ("1712345678001", "Maria Ficticia", None),
        ("1790012345001", COMPANY, None),
        (None, "JOSE MENDEZ ROJAS", None),
    ]
    persons, protected = name_context(parties, "1760001230001", "GAD Municipal de Ejemplo")
    assert set(persons) == {"Maria Ficticia", "JOSE MENDEZ ROJAS"}
    assert set(protected) == {COMPANY, "GAD Municipal de Ejemplo"}
    assert "Buyer Persona" in name_context([], "1712000000001", "Buyer Persona")[0]


# ---------------------------------------------------------------------------------- end to end


def _write(path: Path, rows, schema=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)


def _texts(ocid, rows):
    return [
        {
            "ocid": ocid,
            "kind": k,
            "seq": s,
            "date": "2023-01-02",
            "author_kind": "oferente" if k == "enquiry_question" else "entidad",
            "text": t,
            "source_field": f"tender.enquiries[{s}].x",
            "truncated": False,
            "author_person": p,
        }
        for k, s, t, p in rows
    ]


@pytest.fixture
def lake(tmp_path: Path):
    lake_dir, marts = tmp_path / "lake", tmp_path / "marts"
    texts_dir = tmp_path / "texts"
    ocids = ["ocds-5wno2w-A", "ocds-5wno2w-B", "ocds-5wno2w-C", "ocds-5wno2w-D"]
    _write(
        lake_dir / "processes.parquet",
        [{"ocid": o, "buyer_ruc": "1760001230001", "buyer_name": "GAD Ejemplo"} for o in ocids],
    )
    _write(
        lake_dir / "tenderers.parquet",
        [{"ocid": "ocds-5wno2w-A", "supplier_ruc": None, "supplier_name": PERSON}],
    )
    _write(
        lake_dir / "awards.parquet",
        [{"ocid": "ocds-5wno2w-B", "supplier_ruc": "1790012345001", "supplier_name": COMPANY}],
    )
    _write(
        texts_dir / "process_texts.parquet",
        _texts(
            "ocds-5wno2w-A",
            [
                ("enquiry_question", 0, f"{ON_TOPIC} {PERSON}", False),
                ("enquiry_question", 1, f"{ON_TOPIC}?", False),
            ],
        )
        + _texts(
            "ocds-5wno2w-B",
            [("enquiry_question", 0, f"{ON_TOPIC}?", False), ("enquiry_answer", 0, "Se amplía.", False)],
        )
        + _texts("ocds-5wno2w-C", [("enquiry_question", 0, OFF_TOPIC, False)])
        + _texts("ocds-5wno2w-X", [("enquiry_question", 0, ON_TOPIC, False)]),  # no signal: not flagged
        TEXT_SCHEMA,
    )
    signals = [
        {"ocid": o, "signal_code": "SHORT_TENDER_WINDOW"}
        for o in ("ocds-5wno2w-A", "ocds-5wno2w-B", "ocds-5wno2w-C")
    ]
    _write(
        marts / "process_signals.parquet",
        signals + [{"ocid": "ocds-5wno2w-D", "signal_code": "SINGLE_BIDDER"}],
    )
    _write(
        marts / "process_scores.parquet",
        [{"ocid": o, "winner_ruc": None, "winner_name": None, "winner_kind": None} for o in ocids],
        pa.schema(
            [
                ("ocid", pa.string()),
                ("winner_ruc", pa.string()),
                ("winner_name", pa.string()),
                ("winner_kind", pa.string()),
            ]
        ),
    )
    return lake_dir, marts, texts_dir


def test_source_yields_flagged_processes_with_text_aligned_to_their_own_rows(lake):
    bundles = list(LakeQuoteSource(*lake).bundles())
    assert [b.ocid for b in bundles] == ["ocds-5wno2w-A", "ocds-5wno2w-B", "ocds-5wno2w-C"]
    a, b, c = bundles
    assert [t.seq for t in a.texts] == [0, 1] and PERSON in a.texts[0].text
    assert [t.kind for t in b.texts] == ["enquiry_answer", "enquiry_question"] or len(b.texts) == 2
    assert c.texts[0].text == OFF_TOPIC
    assert PERSON in a.person_names and COMPANY in b.protected_names and "GAD Ejemplo" in a.protected_names
    assert PERSON not in b.person_names  # parties are attached to their own process only
    assert all(x.signals == ("SHORT_TENDER_WINDOW",) for x in bundles)
    assert [x.ocid for x in LakeQuoteSource(*lake).bundles(ocids=["ocds-5wno2w-B"])] == ["ocds-5wno2w-B"]
    assert [x.ocid for x in LakeQuoteSource(*lake).bundles(limit=1)] == ["ocds-5wno2w-A"]


def test_source_reports_missing_inputs(tmp_path: Path):
    with pytest.raises(MissingInputError):
        list(LakeQuoteSource(tmp_path / "lake", tmp_path / "marts").bundles())


def test_build_writes_both_marts_and_is_idempotent(lake, tmp_path: Path):
    out = tmp_path / "out"

    def run():
        sink = ParquetQuoteSink(out)
        report = build_quotes(LakeQuoteSource(*lake), FakeEmbedder(), sink, floor=FLOOR, batch_size=2)
        return report

    first = run()
    quotes = pq.read_table(out / "process_quotes.parquet")
    stats = pq.read_table(out / "process_quote_stats.parquet")
    assert quotes.schema.equals(QUOTES_SCHEMA) and stats.schema.equals(STATS_SCHEMA)
    assert (out / "person_name_tokens.parquet").is_file()
    by_ocid = {r["ocid"]: r for r in stats.to_pylist()}
    assert set(by_ocid) == {"ocds-5wno2w-A", "ocds-5wno2w-B", "ocds-5wno2w-C"}
    assert by_ocid["ocds-5wno2w-A"]["excluded_personal"] == 1 and by_ocid["ocds-5wno2w-A"]["n_quotes"] == 1
    assert by_ocid["ocds-5wno2w-C"]["below_floor"] == 1 and by_ocid["ocds-5wno2w-C"]["n_quotes"] == 0
    stored = quotes.to_pylist()
    assert PERSON not in repr(stored)  # the person's passage never reached the mart
    assert {r["ocid"] for r in stored} == {"ocds-5wno2w-A", "ocds-5wno2w-B"}
    assert first.processes == 3 and first.processes_with_quote == 2 and first.pairs == 1
    assert first.by_signal_with_quote["SHORT_TENDER_WINDOW"] == 2
    before = quotes.to_pylist()
    run()
    assert pq.read_table(out / "process_quotes.parquet").to_pylist() == before
    assert not list(out.glob("*.tmp"))


def test_natural_person_askers_are_read_from_the_bulk_file_and_never_stored(lake, tmp_path: Path):
    import gzip

    import orjson

    raw = tmp_path / "bulk.jsonl.gz"
    release = {
        "ocid": "ocds-5wno2w-C",
        "tender": {
            "enquiries": [
                {
                    "description": "x",
                    "author": {"id": "EC-RUC-1712345678001-9", "name": "Luis Fernando Frank Cassagne"},
                },
                {"description": "y", "author": {"id": "EC-RUC-1790012345001-9", "name": COMPANY}},
            ]
        },
    }
    with gzip.open(raw, "wb") as handle:
        handle.write(orjson.dumps(release) + b"\n")
    bundle = next(b for b in LakeQuoteSource(*lake, raw_path=raw).bundles() if b.ocid == "ocds-5wno2w-C")
    assert "Luis Fernando Frank Cassagne" in bundle.person_names and COMPANY not in bundle.person_names
    leaky = TextRow(
        "enquiry_question",
        0,
        "Presentar el RUC del consorciado LUIS FERNANDO FRANK CASSAGNE",
        None,
        "oferente",
        "f",
        False,
        False,
    )
    assert not judge_texts(ProcessBundle("x", ("SINGLE_BIDDER",), (leaky,), bundle.person_names, ()))[
        0
    ].verdict.eligible
    with pytest.raises(MissingInputError):
        list(LakeQuoteSource(*lake, raw_path=tmp_path / "missing.gz").bundles())
