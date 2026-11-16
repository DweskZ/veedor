from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures" / "vectors"))

from vector_fixture_data import build_vector_lake  # noqa: E402


@pytest.fixture
def vector_lake(tmp_path: Path) -> tuple[Path, Path]:
    return build_vector_lake(tmp_path)


@pytest.fixture(scope="session")
def pg_engine():
    """The configured PostgreSQL (pgvector); skips when unreachable or the extension is unavailable."""
    from sqlalchemy import text

    from veedor.infrastructure.db.session import get_engine

    engine = get_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.commit()
    except Exception as exc:  # noqa: BLE001 - any connection problem means "no database here"
        pytest.skip(f"PostgreSQL with pgvector not reachable: {exc.__class__.__name__}")
    return engine


@pytest.fixture
def vector_session(pg_engine) -> Iterator:
    """A session on a throw-away schema holding its own copy of `process_vectors`."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from veedor.infrastructure.vectors.repository import ProcessVector

    schema = f"vec_test_{uuid.uuid4().hex[:10]}"
    with pg_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = pg_engine.execution_options(schema_translate_map={None: schema})
    ProcessVector.__table__.create(scoped)
    session = sessionmaker(bind=scoped, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        with pg_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
