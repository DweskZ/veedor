"""`find_similar` with an in-memory store (no database, no model)."""

from __future__ import annotations

import pytest

from veedor.use_cases.similar_processes import (
    MAX_K,
    Neighbour,
    ProcessNotIndexed,
    SimilarProcess,
    VectorsUnavailable,
    find_similar,
)


def _neighbour(ocid: str, similarity: float, buyer: str | None = "1760001230001") -> Neighbour:
    return Neighbour(ocid, similarity, 2023, buyer, "Licitación", 100.0, "532100111")


class FakeStore:
    def __init__(self, rows: list[Neighbour] | None = None, error: Exception | None = None) -> None:
        self.rows = rows or []
        self.error = error
        self.calls: list[tuple[str, int, bool]] = []

    def neighbours(self, ocid: str, k: int, same_buyer: bool) -> list[Neighbour]:
        self.calls.append((ocid, k, same_buyer))
        if self.error:
            raise self.error
        return self.rows[:k]


def _names(rucs):
    return {"1760001230001": "GAD Municipal de Ejemplo"}


def test_returns_similar_process_records_in_order_with_buyer_names() -> None:
    store = FakeStore([_neighbour("a", 0.9), _neighbour("b", 0.8, buyer=None), _neighbour("c", 0.7)])
    found = find_similar("q", 2, store=store, buyer_names=_names)
    assert found == [
        SimilarProcess(
            "a", 0.9, 2023, "1760001230001", "GAD Municipal de Ejemplo", "Licitación", 100.0, "532100111"
        ),
        SimilarProcess("b", 0.8, 2023, None, None, "Licitación", 100.0, "532100111"),
    ]
    assert store.calls == [("q", 2, False)]


def test_same_buyer_flag_is_passed_to_the_store() -> None:
    store = FakeStore([_neighbour("a", 0.9)])
    find_similar("q", 5, same_buyer=True, store=store, buyer_names=_names)
    assert store.calls == [("q", 5, True)]


def test_unknown_buyer_name_stays_none() -> None:
    store = FakeStore([_neighbour("a", 0.9, buyer="1760009999001")])
    [item] = find_similar("q", store=store, buyer_names=lambda rucs: {})
    assert item.buyer_ruc == "1760009999001" and item.buyer_name is None


def test_name_lookup_is_skipped_without_buyers() -> None:
    def explode(rucs):
        raise AssertionError("must not be called")

    store = FakeStore([_neighbour("a", 0.9, buyer=None)])
    assert find_similar("q", store=store, buyer_names=explode)[0].buyer_name is None


@pytest.mark.parametrize("k", [0, -1, MAX_K + 1])
def test_k_out_of_range_is_rejected(k: int) -> None:
    with pytest.raises(ValueError):
        find_similar("q", k, store=FakeStore())


def test_unavailable_and_not_indexed_propagate() -> None:
    with pytest.raises(VectorsUnavailable):
        find_similar("q", store=FakeStore(error=VectorsUnavailable("down")))
    with pytest.raises(ProcessNotIndexed):
        find_similar("q", store=FakeStore(error=ProcessNotIndexed("q")))


def test_default_store_raises_unavailable_when_the_database_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy import create_engine

    from veedor.infrastructure.vectors import repository

    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x", connect_args={"connect_timeout": 1})
    monkeypatch.setattr(repository, "get_engine", lambda: engine)
    with pytest.raises(VectorsUnavailable):
        find_similar("ocds-5wno2w-whatever", buyer_names=_names)
