"""Shared counters of the question route: atomic increments, fallbacks, Retry-After (SQLite stands in)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text

from veedor.api.v1.ask import AskLimits
from veedor.infrastructure.db.usage import AskUsageStore
from veedor.use_cases.ask import DailyBudget

pytestmark = pytest.mark.filterwarnings("ignore:The default datetime adapter:DeprecationWarning")


@pytest.fixture
def store(tmp_path) -> AskUsageStore:
    engine = create_engine(f"sqlite:///{tmp_path / 'usage.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE ask_usage (bucket VARCHAR(96) PRIMARY KEY, used INTEGER NOT NULL, "
                "updated_at TIMESTAMP NOT NULL)"
            )
        )
    return AskUsageStore(engine)


class Broken:
    def consume(self, bucket: str, limit: int) -> bool:
        raise RuntimeError("database down")

    def used(self, bucket: str) -> int:
        raise RuntimeError("database down")


def test_consume_counts_up_to_the_limit_and_no_further(store: AskUsageStore) -> None:
    assert [store.consume("b", 3) for _ in range(5)] == [True, True, True, False, False]
    assert store.used("b") == 3  # the refused calls did not count
    assert store.consume("other", 1) and not store.consume("other", 1)
    assert not store.consume("zero", 0) and store.used("zero") == 0


def test_two_store_objects_share_one_count_like_two_workers(store: AskUsageStore) -> None:
    second = AskUsageStore(store._engine)  # a second worker with its own pool
    assert [
        store.consume("day", 4),
        second.consume("day", 4),
        store.consume("day", 4),
        second.consume("day", 4),
    ] == [True] * 4
    assert not store.consume("day", 4) and not second.consume("day", 4)


def test_the_daily_budget_is_shared_and_survives_a_restart(store: AskUsageStore) -> None:
    clock = lambda: datetime(2026, 11, 16, 12, tzinfo=UTC)  # noqa: E731
    first = DailyBudget(2, clock, store=store, fallback_limit=1)
    assert first.try_consume()
    restarted = DailyBudget(
        2, clock, store=store, fallback_limit=1
    )  # a new process: the count is in the database
    assert restarted.try_consume() and not restarted.try_consume() and not first.try_consume()
    tomorrow = DailyBudget(2, lambda: datetime(2026, 11, 17, 0, 1, tzinfo=UTC), store=store, fallback_limit=1)
    assert tomorrow.try_consume()


def test_when_the_database_fails_the_budget_counts_in_memory_with_the_worker_share() -> None:
    budget = DailyBudget(10, store=Broken(), fallback_limit=2)
    assert [budget.try_consume() for _ in range(4)] == [True, True, False, False]


def test_client_limits_are_shared_and_fall_back_in_memory(store: AskUsageStore) -> None:
    one, two = AskLimits(2, 100, store), AskLimits(2, 100, store)
    assert [one.allow("203.0.113.9"), two.allow("203.0.113.9"), one.allow("203.0.113.9")] == [
        True,
        True,
        False,
    ]
    assert 1 <= one.retry_after("203.0.113.9") <= 60
    assert two.allow("198.51.100.1")  # another client has its own counter
    broken = AskLimits(1, 100, Broken())
    assert [broken.allow("x"), broken.allow("x")] == [True, False]  # in memory for this worker
    assert broken.retry_after("x") >= 1


def test_only_a_hash_of_the_client_is_stored(store: AskUsageStore) -> None:
    AskLimits(5, 50, store).allow("203.0.113.77")
    with store._engine.connect() as connection:
        buckets = [row[0] for row in connection.execute(text("SELECT bucket FROM ask_usage"))]
    assert buckets and all("203.0.113.77" not in b for b in buckets)


def test_postgres_counts_exactly_under_concurrency() -> None:
    """On the configured PostgreSQL (skipped when unreachable): 16 threads, one bucket, limit 5: 5 counted."""
    import uuid
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    from alembic.config import Config

    from alembic import command
    from veedor.infrastructure.db.session import get_engine

    engine = get_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL not reachable: {exc.__class__.__name__}")
    command.upgrade(Config(str(Path(__file__).resolve().parents[3] / "alembic.ini")), "head")
    store = AskUsageStore(engine)
    bucket = f"test:{uuid.uuid4().hex}"
    try:
        with ThreadPoolExecutor(16) as pool:
            counted = sum(pool.map(lambda _: store.consume(bucket, 5), range(40)))
        assert counted == 5 and store.used(bucket) == 5
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM ask_usage WHERE bucket = :b"), {"b": bucket})
