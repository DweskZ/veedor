"""FastAPI dependencies (overridable in tests)."""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from veedor.core.settings import get_settings
from veedor.infrastructure.db.repositories import SqlReviewRepository
from veedor.infrastructure.db.session import get_session
from veedor.infrastructure.lake.reader import LakeReader
from veedor.use_cases.queries.ports import LakePort
from veedor.use_cases.queries.processes import name_context, process_exists
from veedor.use_cases.reviews import ReviewAuthError, ReviewsDisabledError, ReviewService

_BEARER = re.compile(r"(?i:bearer) ([!-~]+)")
MAX_PAGE_SIZE = 100
MAX_OFFSET = 1_000_000  # deepest row a caller can page to; also keeps OFFSET far from INT64 overflow
DEFAULT_PAGE_SIZE = 25


@lru_cache
def get_reader() -> LakeReader:
    settings = get_settings()
    return LakeReader(settings.lake_dir, settings.marts_dir, threads=settings.lake_threads)


def get_lake(reader: Annotated[LakeReader, Depends(get_reader)]) -> LakePort:
    return reader


Lake = Annotated[LakePort, Depends(get_lake)]


def get_review_service(session: Annotated[Session, Depends(get_session)], lake: Lake) -> ReviewService:
    return ReviewService(
        SqlReviewRepository(session),
        lambda ocid: process_exists(lake, ocid),
        lambda ocid: name_context(lake, ocid),
    )


@dataclass(frozen=True, slots=True)
class ReviewPolicy:
    enabled: bool
    token: str | None

    @property
    def can_write(self) -> bool:
        """Writing needs the flag and a configured token; without a token it stays disabled."""
        return self.enabled and self.token is not None


def get_review_policy() -> ReviewPolicy:
    settings = get_settings()
    return ReviewPolicy(settings.reviews_enabled, (settings.reviews_token or "").strip() or None)


Policy = Annotated[ReviewPolicy, Depends(get_review_policy)]


def authorize_review_write(request: Request, policy: Policy) -> None:
    """Dependency for POST: 403 when disabled, 401 unless the bearer token matches (constant time)."""
    if not policy.can_write:
        raise ReviewsDisabledError
    # Exactly "Bearer <token>" (scheme case-insensitive, one space, no other scheme or extra words).
    match = _BEARER.fullmatch(request.headers.get("authorization", ""))
    expected = (policy.token or "").encode()
    if match is None or not hmac.compare_digest(match.group(1).encode(), expected):
        raise ReviewAuthError


class Pagination(BaseModel):
    page: int
    page_size: int


def get_pagination(
    page: Annotated[int, Query(ge=1, le=MAX_OFFSET, description="1-based page number.")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=MAX_PAGE_SIZE, description="Rows per page (max 100).")
    ] = DEFAULT_PAGE_SIZE,
) -> Pagination:
    if (page - 1) * page_size > MAX_OFFSET:
        raise RequestValidationError(
            [
                {
                    "loc": ("query", "page"),
                    "msg": f"page * page_size must not exceed {MAX_OFFSET}",
                    "type": "value_error",
                }
            ]
        )
    return Pagination(page=page, page_size=page_size)


Paging = Annotated[Pagination, Depends(get_pagination)]
Reviews = Annotated[ReviewService, Depends(get_review_service)]
