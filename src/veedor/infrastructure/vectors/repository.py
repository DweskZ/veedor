"""PostgreSQL + pgvector storage for process embeddings.

Only SQLAlchemy constructs with bound parameters are used (no string-built SQL), so a session whose
engine has a `schema_translate_map` (tests) works unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, Index, Integer, String, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError, ProgrammingError
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from veedor.infrastructure.db.models import Base
from veedor.infrastructure.db.session import get_engine
from veedor.infrastructure.vectors.embedding import DIMENSION
from veedor.use_cases.similar_processes import Neighbour, ProcessNotIndexed, VectorsUnavailable

HNSW_EF_SEARCH = 100  # candidate list per query (pgvector default 40); recall/latency trade-off
INDEX_NAME = "ix_process_vectors_embedding_hnsw"


class ProcessVector(Base):
    """Mirrors migration 0002. No text column: only the vector and non-sensitive metadata."""

    __tablename__ = "process_vectors"
    __table_args__ = (
        Index("ix_process_vectors_buyer_ruc", "buyer_ruc"),
        Index(
            INDEX_NAME,
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    ocid: Mapped[str] = mapped_column(String(160), primary_key=True)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(DIMENSION), nullable=False)
    year: Mapped[int | None] = mapped_column(Integer)
    buyer_ruc: Mapped[str | None] = mapped_column(String(20))
    method: Mapped[str | None] = mapped_column(String(200))
    award_total: Mapped[float | None] = mapped_column(Float)
    main_cpc: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


@dataclass(frozen=True, slots=True)
class VectorRow:
    ocid: str
    model: str
    content_hash: str
    embedding: np.ndarray
    year: int | None
    buyer_ruc: str | None
    method: str | None
    award_total: float | None
    main_cpc: str | None


@dataclass(frozen=True, slots=True)
class IndexStatus:
    rows: int
    models: dict[str, int]
    index_definition: str | None
    last_build: datetime | None


@contextmanager
def translate_db_errors() -> Iterator[None]:
    try:
        yield
    except (OperationalError, InterfaceError) as exc:
        raise VectorsUnavailable("The vector database is not reachable.") from exc
    except ProgrammingError as exc:
        raise VectorsUnavailable("The vector table is missing; run `alembic upgrade head`.") from exc
    except DBAPIError as exc:  # e.g. the vector type does not exist
        raise VectorsUnavailable("The vector index cannot be used.") from exc


class PgVectorStore:
    """Implements `VectorStore` and the write side used by the build command."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @classmethod
    def from_settings(cls) -> PgVectorStore:
        return cls(sessionmaker(bind=get_engine(), expire_on_commit=False)())

    # ------------------------------------------------------------------ read side

    def neighbours(self, ocid: str, k: int, same_buyer: bool) -> list[Neighbour]:
        with translate_db_errors():
            query = self._session.execute(
                select(ProcessVector.embedding, ProcessVector.buyer_ruc).where(ProcessVector.ocid == ocid)
            ).first()
            if query is None:
                if not self._session.scalar(select(ProcessVector.ocid).limit(1)):
                    raise VectorsUnavailable("The vector index is empty; run `veedor vectors build`.")
                raise ProcessNotIndexed(ocid)
            vector, buyer = query
            if same_buyer and not buyer:
                return []
            distance = ProcessVector.embedding.cosine_distance(vector)
            stmt = select(
                ProcessVector.ocid,
                distance.label("distance"),
                ProcessVector.year,
                ProcessVector.buyer_ruc,
                ProcessVector.method,
                ProcessVector.award_total,
                ProcessVector.main_cpc,
            ).where(ProcessVector.ocid != ocid)
            if same_buyer:
                stmt = stmt.where(ProcessVector.buyer_ruc == buyer)
            stmt = stmt.order_by(distance).limit(k)
            self._tune_search(filtered=same_buyer)
            rows = self._session.execute(stmt).all()
            self._session.rollback()  # ends the read transaction; SET LOCAL settings go with it
        return [
            Neighbour(
                ocid=r.ocid,
                similarity=1.0 - float(r.distance),
                year=r.year,
                buyer_ruc=r.buyer_ruc,
                method=r.method,
                award_total=r.award_total,
                main_cpc=r.main_cpc,
            )
            for r in rows
        ]

    def _tune_search(self, *, filtered: bool) -> None:
        self._session.execute(text(f"SET LOCAL hnsw.ef_search = {int(HNSW_EF_SEARCH)}"))
        if filtered:  # filters apply after the ANN scan: keep scanning until k rows pass
            self._session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))

    def existing(self, ocids: Sequence[str]) -> dict[str, tuple[str, str]]:
        """``{ocid: (content_hash, model)}`` for the given ocids that are already stored."""
        out: dict[str, tuple[str, str]] = {}
        with translate_db_errors():
            for start in range(0, len(ocids), 10_000):
                chunk = list(ocids[start : start + 10_000])
                stmt = select(ProcessVector.ocid, ProcessVector.content_hash, ProcessVector.model)
                for ocid, content_hash, model in self._session.execute(
                    stmt.where(ProcessVector.ocid.in_(chunk))
                ):
                    out[ocid] = (content_hash, model)
        return out

    def count(self) -> int:
        with translate_db_errors():
            return int(self._session.scalar(select(func.count()).select_from(ProcessVector)) or 0)

    def status(self) -> IndexStatus:
        with translate_db_errors():
            rows = self.count()
            models = dict(
                self._session.execute(
                    select(ProcessVector.model, func.count()).group_by(ProcessVector.model)
                ).all()
            )
            last = self._session.scalar(select(func.max(ProcessVector.created_at)))
            definition = self._session.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE tablename = 'process_vectors' AND indexname = :n"
                ),
                {"n": INDEX_NAME},
            )
        return IndexStatus(rows=rows, models=models, index_definition=definition, last_build=last)

    def metadata_arrays(self) -> tuple[list[str], list[str | None]]:
        """``(ocids, main_cpc)`` of every stored row, for evaluation baselines."""
        with translate_db_errors():
            rows = self._session.execute(select(ProcessVector.ocid, ProcessVector.main_cpc)).all()
        return [r.ocid for r in rows], [r.main_cpc for r in rows]

    def vectors_for(self, ocids: Sequence[str]) -> dict[str, np.ndarray]:
        with translate_db_errors():
            rows = self._session.execute(
                select(ProcessVector.ocid, ProcessVector.embedding).where(ProcessVector.ocid.in_(list(ocids)))
            ).all()
        return {r.ocid: np.asarray(r.embedding, dtype=np.float32) for r in rows}

    # ----------------------------------------------------------------- write side

    def upsert(self, rows: Sequence[VectorRow]) -> None:
        if not rows:
            return
        values = [
            {
                "ocid": r.ocid,
                "model": r.model,
                "content_hash": r.content_hash,
                "embedding": r.embedding,
                "year": r.year,
                "buyer_ruc": r.buyer_ruc,
                "method": r.method,
                "award_total": r.award_total,
                "main_cpc": r.main_cpc,
            }
            for r in rows
        ]
        stmt = pg_insert(ProcessVector)
        update = {
            col: getattr(stmt.excluded, col)
            for col in (
                "model",
                "content_hash",
                "embedding",
                "year",
                "buyer_ruc",
                "method",
                "award_total",
                "main_cpc",
            )  # fmt: skip
        } | {"created_at": func.now()}
        with translate_db_errors():
            self._session.execute(stmt.on_conflict_do_update(index_elements=["ocid"], set_=update), values)
            self._session.commit()
