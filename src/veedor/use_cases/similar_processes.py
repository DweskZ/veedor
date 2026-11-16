"""Similar processes: nearest neighbours of a process in the embedding space.

`find_similar` is the interface other areas call. It needs a vector store (PostgreSQL + pgvector in
production, any `VectorStore` in tests) and, optionally, a buyer-name lookup (the store keeps the buyer
RUC only). Callers that expose the result over HTTP must mask it (`MaskedModel`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

MAX_K = 50

BuyerNames = Callable[[Sequence[str]], Mapping[str, str]]


class VectorsUnavailable(Exception):
    """The vector index or its database is missing, empty or unreachable."""


class ProcessNotIndexed(Exception):
    """The process has no vector (unknown, catalogue purchase, or no embeddable text)."""

    def __init__(self, ocid: str) -> None:
        self.ocid = ocid
        super().__init__(f"process {ocid!r} is not in the vector index")


@dataclass(frozen=True, slots=True)
class SimilarProcess:
    ocid: str
    similarity: float  # cosine similarity in [-1, 1]; 1 means the same embedded text
    year: int | None
    buyer_ruc: str | None
    buyer_name: str | None
    method: str | None
    award_total: float | None
    main_cpc: str | None


@dataclass(frozen=True, slots=True)
class Neighbour:
    """One row returned by a store: everything stored with the vector, plus the similarity."""

    ocid: str
    similarity: float
    year: int | None
    buyer_ruc: str | None
    method: str | None
    award_total: float | None
    main_cpc: str | None


class VectorStore(Protocol):
    def neighbours(self, ocid: str, k: int, same_buyer: bool) -> list[Neighbour]:
        """Nearest neighbours of `ocid`, itself excluded.

        Raises `VectorsUnavailable` (no table, no rows, no database) or `ProcessNotIndexed`.
        """
        ...


def find_similar(
    ocid: str,
    k: int = 10,
    same_buyer: bool = False,
    *,
    store: VectorStore | None = None,
    buyer_names: BuyerNames | None = None,
) -> list[SimilarProcess]:
    """Return up to `k` processes whose purchased object is closest to `ocid`'s, best first.

    `same_buyer` keeps only processes of the same buying entity. Raises `VectorsUnavailable` when the
    index or the database is missing, and `ProcessNotIndexed` when `ocid` has no vector.
    """
    if not 1 <= k <= MAX_K:
        raise ValueError(f"k must be between 1 and {MAX_K}")
    if store is None:
        store = _default_store()
    found = store.neighbours(ocid, k, same_buyer)
    names = _lookup_names(buyer_names, found)
    return [
        SimilarProcess(
            ocid=n.ocid,
            similarity=n.similarity,
            year=n.year,
            buyer_ruc=n.buyer_ruc,
            buyer_name=names.get(n.buyer_ruc) if n.buyer_ruc else None,
            method=n.method,
            award_total=n.award_total,
            main_cpc=n.main_cpc,
        )
        for n in found
    ]


def _lookup_names(buyer_names: BuyerNames | None, found: Sequence[Neighbour]) -> Mapping[str, str]:
    if buyer_names is None:
        buyer_names = _default_buyer_names()
    rucs = sorted({n.buyer_ruc for n in found if n.buyer_ruc})
    return buyer_names(rucs) if rucs else {}


def _default_store() -> VectorStore:
    from veedor.infrastructure.vectors.repository import PgVectorStore

    return PgVectorStore.from_settings()


def _default_buyer_names() -> BuyerNames:
    from veedor.infrastructure.vectors.names import lake_buyer_names

    return lake_buyer_names
