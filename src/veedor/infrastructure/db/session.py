"""Engine and session factory (lazy: importing this module never connects)."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from veedor.core.settings import get_settings

CONNECT_TIMEOUT_SECONDS = 3


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


def get_session() -> Iterator[Session]:
    with sessionmaker(bind=get_engine(), expire_on_commit=False)() as session:
        yield session
