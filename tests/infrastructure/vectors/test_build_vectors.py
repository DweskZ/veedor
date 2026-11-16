"""Text composition (privacy) and the idempotent, deduplicating build, with the fake embedder."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import vector_fixture_data as fx

from veedor.infrastructure.vectors.embedding import DIMENSION, FakeEmbedder
from veedor.infrastructure.vectors.source import LakeProcessSource
from veedor.use_cases.build_vectors import (
    STATUS_FULL,
    STATUS_NO_DESCRIPTION,
    STATUS_NO_TEXT,
    STATUS_WITHHELD,
    ProcessRecord,
    build_vectors,
    compose_text,
)


class MemoryStore:
    def __init__(self) -> None:
        self.rows: dict[str, object] = {}

    def existing(self, ocids):
        return {o: (self.rows[o].content_hash, self.rows[o].model) for o in ocids if o in self.rows}

    def upsert(self, rows) -> None:
        for row in rows:
            self.rows[row.ocid] = row


class CountingEmbedder(FakeEmbedder):
    def __init__(self) -> None:
        super().__init__()
        self.texts: list[str] = []

    def embed(self, texts):
        self.texts.extend(texts)
        return super().embed(texts)


def _record(**kw) -> ProcessRecord:
    base = {
        "ocid": "ocds-5wno2w-x", "year": 2023, "buyer_ruc": fx.BUYER_RUC, "buyer_name": fx.BUYER_NAME,
        "method": "Licitación", "award_total": 1.0, "main_cpc": "532100111",
        "cpc_description": "Obras viales", "description": "Asfaltado de calles",
    }  # fmt: skip
    return ProcessRecord(**(base | kw))


def test_full_text_joins_cpc_and_description() -> None:
    assert compose_text(_record()) == ("Obras viales. Asfaltado de calles", STATUS_FULL)


def test_no_description_uses_cpc_only() -> None:
    assert compose_text(_record(description=None)) == ("Obras viales", STATUS_NO_DESCRIPTION)


def test_description_naming_a_known_person_is_withheld_and_never_embedded() -> None:
    text, status = compose_text(
        _record(
            description=f"Servicio de {fx.NATURAL_NAME}",
            parties=((fx.NATURAL_RUC, fx.NATURAL_NAME),),
        )
    )
    assert (text, status) == ("Obras viales", STATUS_WITHHELD)


def test_masked_winner_withholds_the_description() -> None:
    record = _record(
        winner=(fx.NATURAL_RUC, fx.NATURAL_NAME, "natural_person"), description="Compra de sillas"
    )
    assert compose_text(record) == ("Obras viales", STATUS_WITHHELD)


def test_identifiers_and_honorifics_withhold_the_description() -> None:
    for description in (
        f"Contrato cédula {fx.CEDULA}",
        "Pago al Ing. Juan Pérez por obras",
        "RUC 1712345678001 x",
    ):
        text, status = compose_text(_record(description=description))
        assert (text, status) == ("Obras viales", STATUS_WITHHELD), description


def test_withheld_without_cpc_yields_no_text() -> None:
    assert compose_text(_record(cpc_description=None, description=f"Contrato cédula {fx.CEDULA}")) == (
        None,
        STATUS_NO_TEXT,
    )


def test_description_only_variant_drops_the_cpc_text() -> None:
    text, _ = compose_text(_record(), include_cpc=False)
    assert text == "Asfaltado de calles"


def test_long_text_is_bounded() -> None:
    text, _ = compose_text(_record(description="x " * 5000))
    assert text is not None and len(text) <= 1000


def _source(lake: tuple[Path, Path]) -> LakeProcessSource:
    return LakeProcessSource(*lake)


def test_source_skips_catalogue_and_rows_without_any_text(vector_lake) -> None:
    ocids = {r.ocid for r in _source(vector_lake).records()}
    assert fx.OCID_CATALOGUE not in ocids and fx.OCID_NO_TEXT not in ocids
    assert fx.OCID_ROAD_1 in ocids and fx.OCID_PERSON in ocids


def test_source_attaches_parties_and_winner(vector_lake) -> None:
    by_ocid = {r.ocid: r for r in _source(vector_lake).records()}
    assert by_ocid[fx.OCID_PERSON].winner == (fx.NATURAL_RUC, fx.NATURAL_NAME, "natural_person")
    assert (fx.NATURAL_RUC, fx.NATURAL_NAME) in by_ocid[fx.OCID_PERSON].parties
    assert by_ocid[fx.OCID_MED_1].winner is None


def test_source_limit_and_ocid_filter(vector_lake) -> None:
    source = _source(vector_lake)
    assert len(list(source.records(limit=3))) == 3
    assert [r.ocid for r in source.records(None, [fx.OCID_MED_2])] == [fx.OCID_MED_2]


def test_build_embeds_only_safe_text_and_is_idempotent(vector_lake) -> None:
    store, embedder = MemoryStore(), CountingEmbedder()
    first = build_vectors(_source(vector_lake), embedder, store)
    assert fx.OCID_CATALOGUE not in store.rows and fx.OCID_NO_TEXT not in store.rows
    assert fx.OCID_PERSON_NO_CPC not in store.rows  # nothing safe to embed
    assert first.statuses[STATUS_WITHHELD] == 2  # the person-named row and the cédula row
    joined = " ".join(embedder.texts).lower()
    assert fx.NATURAL_NAME.lower() not in joined and fx.CEDULA not in joined
    for row in store.rows.values():
        assert not hasattr(row, "description") and not hasattr(row, "text")
        assert row.embedding.shape == (DIMENSION,) and abs(float(np.linalg.norm(row.embedding)) - 1) < 1e-5

    embedder.texts.clear()
    second = build_vectors(_source(vector_lake), embedder, store)
    assert second.records_embedded == 0 and second.unchanged_skipped == first.records_embedded
    assert embedder.texts == []


def test_identical_texts_are_embedded_once_and_mapped_back(vector_lake) -> None:
    store, embedder = MemoryStore(), CountingEmbedder()
    report = build_vectors(_source(vector_lake), embedder, store)
    withheld_text = f"{fx.CPC_ROADS}"
    assert embedder.texts.count(withheld_text) == 1  # two withheld road rows share it
    assert report.records_embedded > report.unique_texts
    assert store.rows[fx.OCID_PERSON].content_hash == store.rows[fx.OCID_CEDULA].content_hash
    assert np.allclose(store.rows[fx.OCID_PERSON].embedding, store.rows[fx.OCID_CEDULA].embedding)


def test_changed_model_triggers_re_embedding(vector_lake) -> None:
    store = MemoryStore()
    build_vectors(_source(vector_lake), CountingEmbedder(), store)
    other = CountingEmbedder()
    other.model_name = "another-model"
    report = build_vectors(_source(vector_lake), other, store)
    assert report.unchanged_skipped == 0 and report.records_embedded > 0


def test_limit_builds_a_prefix_and_a_second_run_resumes(vector_lake) -> None:
    store = MemoryStore()
    partial = build_vectors(_source(vector_lake), CountingEmbedder(), store, limit=3)
    assert len(store.rows) == partial.records_embedded <= 3
    rest = build_vectors(_source(vector_lake), CountingEmbedder(), store)
    assert rest.unchanged_skipped == partial.records_embedded
    assert len(store.rows) == partial.records_embedded + rest.records_embedded


def test_progress_is_reported_per_chunk(vector_lake) -> None:
    seen = []
    build_vectors(_source(vector_lake), FakeEmbedder(), MemoryStore(), chunk_size=2, progress=seen.append)
    assert seen and seen[-1].done == seen[-1].total
    assert [p.done for p in seen] == sorted(p.done for p in seen)


def test_fake_embedder_is_deterministic_and_similar_texts_are_closer() -> None:
    e = FakeEmbedder()
    a, b, c = e.embed(["asfaltado de vías", "asfaltado de calles", "compra de antibióticos"])
    assert np.array_equal(a, e.embed(["asfaltado de vías"])[0])
    assert float(a @ b) > float(a @ c)
