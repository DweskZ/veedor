"""PostgreSQL + pgvector adapter, on a throw-away schema (skipped when PostgreSQL is unreachable)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from veedor.infrastructure.vectors.embedding import DIMENSION
from veedor.infrastructure.vectors.repository import PgVectorStore, VectorRow
from veedor.use_cases.similar_processes import ProcessNotIndexed, VectorsUnavailable, find_similar


def _unit(*hot: int) -> np.ndarray:
    v = np.zeros(DIMENSION, dtype=np.float32)
    v[list(hot)] = 1.0
    return v / np.linalg.norm(v)


def _row(ocid: str, vector: np.ndarray, buyer: str | None = "B1", cpc: str | None = "532100111") -> VectorRow:
    return VectorRow(ocid, "m", f"hash-{ocid}", vector, 2023, buyer, "Licitación", 10.0, cpc)


@pytest.fixture
def store(vector_session) -> PgVectorStore:
    store = PgVectorStore(vector_session)
    store.upsert(
        [
            _row("q", _unit(0, 1)),
            _row("near", _unit(0, 1, 2)),
            _row("mid", _unit(1, 5, 6), buyer="B2"),
            _row("far", _unit(100, 101), buyer="B1"),
            _row("nobuyer", _unit(0, 3), buyer=None),
        ]
    )
    return store


def test_neighbours_are_ordered_by_cosine_and_exclude_the_query(store: PgVectorStore) -> None:
    found = store.neighbours("q", 3, False)
    assert [n.ocid for n in found] == ["near", "nobuyer", "mid"]
    assert found[0].similarity == pytest.approx(float(_unit(0, 1) @ _unit(0, 1, 2)), abs=1e-5)
    assert all(a.similarity >= b.similarity for a, b in zip(found, found[1:], strict=False))
    assert found[0].year == 2023 and found[0].method == "Licitación" and found[0].award_total == 10.0


def test_same_buyer_filters_and_keeps_order(store: PgVectorStore) -> None:
    assert [n.ocid for n in store.neighbours("q", 5, True)] == ["near", "far"]


def test_same_buyer_for_a_query_without_buyer_is_empty(store: PgVectorStore) -> None:
    assert store.neighbours("nobuyer", 5, True) == []


def test_unknown_ocid_is_not_indexed(store: PgVectorStore) -> None:
    with pytest.raises(ProcessNotIndexed):
        store.neighbours("missing", 3, False)


def test_empty_table_is_unavailable(vector_session) -> None:
    with pytest.raises(VectorsUnavailable):
        PgVectorStore(vector_session).neighbours("q", 3, False)


def test_injection_in_ocid_is_just_a_missing_key(store: PgVectorStore) -> None:
    with pytest.raises(ProcessNotIndexed):
        store.neighbours("q'; DROP TABLE process_vectors; --", 3, False)
    assert store.count() == 5


def test_upsert_is_idempotent_and_updates_in_place(store: PgVectorStore) -> None:
    store.upsert([_row("near", _unit(7, 8))])
    assert store.count() == 5
    assert store.existing(["near", "q", "missing"]) == {"near": ("hash-near", "m"), "q": ("hash-q", "m")}
    assert np.allclose(store.vectors_for(["near"])["near"], _unit(7, 8), atol=1e-6)


def test_metadata_arrays(store: PgVectorStore) -> None:
    ocids, cpcs = store.metadata_arrays()
    assert sorted(ocids) == ["far", "mid", "near", "nobuyer", "q"] and set(cpcs) == {"532100111"}


def test_find_similar_end_to_end_with_the_store(store: PgVectorStore) -> None:
    found = find_similar("q", 2, store=store, buyer_names=lambda rucs: {"B1": "Entidad Uno"})
    assert [f.ocid for f in found] == ["near", "nobuyer"]
    assert found[0].buyer_name == "Entidad Uno" and found[1].buyer_name is None


def test_unreachable_database_is_unavailable() -> None:
    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x", connect_args={"connect_timeout": 1})
    with pytest.raises(VectorsUnavailable):
        PgVectorStore(sessionmaker(bind=engine)()).neighbours("q", 3, False)


def test_migration_creates_the_table_and_an_hnsw_cosine_index(pg_engine) -> None:
    from alembic.config import Config

    from alembic import command

    command.upgrade(Config(str(Path(__file__).resolve().parents[3] / "alembic.ini")), "head")
    inspector = inspect(pg_engine)
    columns = {c["name"] for c in inspector.get_columns("process_vectors")}
    assert columns == {
        "ocid", "model", "content_hash", "embedding", "year", "buyer_ruc", "method", "award_total",
        "main_cpc", "created_at",
    }  # fmt: skip
    assert "description" not in columns  # no text column: the raw description is never stored
    index = next(i for i in inspector.get_indexes("process_vectors") if i["name"].endswith("hnsw"))
    assert index["dialect_options"]["postgresql_using"] == "hnsw"
    assert index["dialect_options"]["postgresql_ops"] == {"embedding": "vector_cosine_ops"}
