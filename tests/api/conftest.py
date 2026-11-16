from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures" / "api"))

from api_fixture_data import REVIEW_TOKEN, build_fixture_data  # noqa: E402

from veedor.api.deps import ReviewPolicy, get_reader, get_review_policy  # noqa: E402
from veedor.api.main import create_app  # noqa: E402
from veedor.infrastructure.lake.reader import LakeReader  # noqa: E402


@pytest.fixture
def lake_dirs(tmp_path: Path) -> tuple[Path, Path]:
    return build_fixture_data(tmp_path)


def _enabled_policy() -> ReviewPolicy:
    return ReviewPolicy(enabled=True, token=REVIEW_TOKEN)


@pytest.fixture
def client(lake_dirs: tuple[Path, Path]) -> Iterator[TestClient]:
    """API over the synthetic lake, with reviews enabled and the test token configured."""
    app = create_app()
    app.dependency_overrides[get_reader] = lambda: LakeReader(*lake_dirs)
    app.dependency_overrides[get_review_policy] = _enabled_policy
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def default_client(lake_dirs: tuple[Path, Path]) -> Iterator[TestClient]:
    """API with the production defaults for reviews (disabled, no token)."""
    app = create_app()
    app.dependency_overrides[get_reader] = lambda: LakeReader(*lake_dirs)
    app.dependency_overrides[get_review_policy] = lambda: ReviewPolicy(enabled=False, token=None)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def empty_client(tmp_path: Path) -> Iterator[TestClient]:
    """API whose lake and marts directories hold no files."""
    app = create_app()
    app.dependency_overrides[get_reader] = lambda: LakeReader(tmp_path / "lake", tmp_path / "marts")
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    from veedor.api.security import review_rate_limiter

    review_rate_limiter.reset()


@pytest.fixture(scope="session")
def migrated_engine():
    """Engine on the configured PostgreSQL, migrated with Alembic; skips when unreachable."""
    from alembic.config import Config
    from sqlalchemy import text

    from alembic import command
    from veedor.infrastructure.db.session import get_engine

    engine = get_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any connection problem means "no database here"
        pytest.skip(f"PostgreSQL not reachable: {exc.__class__.__name__}")
    command.upgrade(Config(str(Path(__file__).resolve().parents[2] / "alembic.ini")), "head")
    return engine


@pytest.fixture
def db_client(client: TestClient, migrated_engine) -> Iterator[TestClient]:
    """The API with real review storage; test rows are removed afterwards."""
    from sqlalchemy import text

    yield client
    with migrated_engine.begin() as connection:
        connection.execute(text("DELETE FROM reviews WHERE ocid LIKE 'ocds-5wno2w-test-%'"))


@pytest.fixture
def no_db_client(lake_dirs: tuple[Path, Path]) -> Iterator[TestClient]:
    """API whose review database is unreachable (closed port)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from veedor.infrastructure.db.session import get_session

    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x", connect_args={"connect_timeout": 1})

    def broken_session():
        with sessionmaker(bind=engine)() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_reader] = lambda: LakeReader(*lake_dirs)
    app.dependency_overrides[get_session] = broken_session
    app.dependency_overrides[get_review_policy] = _enabled_policy
    with TestClient(app) as test_client:
        yield test_client
