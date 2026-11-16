"""PostgreSQL implementation of the review repository."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from veedor.infrastructure.db.models import Review
from veedor.use_cases.reviews import ReviewRecord, ReviewStoreUnavailableError


@contextmanager
def _translate_db_errors() -> Iterator[None]:
    try:
        yield
    except (OperationalError, InterfaceError) as exc:
        raise ReviewStoreUnavailableError("The review database is not reachable.") from exc
    except ProgrammingError as exc:
        raise ReviewStoreUnavailableError(
            "The review schema is missing; run `alembic upgrade head`."
        ) from exc


def _record(row: Review) -> ReviewRecord:
    return ReviewRecord(
        id=row.id,
        ocid=row.ocid,
        status=row.status,
        note=row.note,
        reviewer=row.reviewer,
        created_at=row.created_at,
    )


class SqlReviewRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, ocid: str, status: str, note: str | None, reviewer: str | None) -> ReviewRecord:
        with _translate_db_errors():
            row = Review(ocid=ocid, status=status, note=note, reviewer=reviewer)
            self._session.add(row)
            self._session.commit()
            self._session.refresh(row)
            return _record(row)

    def list_for(self, ocid: str) -> list[ReviewRecord]:
        with _translate_db_errors():
            rows = self._session.scalars(
                select(Review).where(Review.ocid == ocid).order_by(Review.created_at.desc(), Review.id.desc())
            )
            return [_record(row) for row in rows]
