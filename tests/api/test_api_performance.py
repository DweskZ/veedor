"""API-level behaviour of the performance work: cached /stats and the data build timestamp."""

from __future__ import annotations

import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from veedor.api.deps import get_reader
from veedor.api.main import create_app
from veedor.infrastructure.lake.reader import LakeReader
from veedor.use_cases.queries import stats

API = "/api/v1"


@pytest.fixture
def shared_client(lake_dirs):
    """One reader shared across requests, like production (`get_reader` is cached)."""
    stats._cached = None
    reader = LakeReader(*lake_dirs, refresh_interval=0)
    app = create_app()
    app.dependency_overrides[get_reader] = lambda: reader
    with TestClient(app) as client:
        yield client, reader, lake_dirs
    stats._cached = None


def test_stats_hit_the_lake_once_until_a_rebuild(shared_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, reader, (_, marts) = shared_client
    calls = []
    real = reader.fetch
    monkeypatch.setattr(reader, "fetch", lambda *a, **k: calls.append(1) or real(*a, **k))
    first = client.get(f"{API}/stats").json()
    used = len(calls)
    assert client.get(f"{API}/stats").json() == first
    assert len(calls) == used

    path = marts / "process_scores.parquet"
    pq.write_table(pq.read_table(path).slice(0, 2), path)
    after = client.get(f"{API}/stats").json()
    assert after["processes_scored"] == 2 and first["processes_scored"] == 5


def test_stats_still_report_table_availability_from_cache(shared_client) -> None:
    client, _, _ = shared_client
    body = client.get(f"{API}/stats").json()
    assert body["available_tables"]["process_scores"] is True
    assert client.get(f"{API}/stats").json()["available_tables"] == body["available_tables"]


def test_health_shows_the_data_build_timestamp(shared_client) -> None:
    client, _, (_, marts) = shared_client
    assert client.get(f"{API}/health").json()["data_built_at"] is None
    (marts / "build_summary.json").write_text("{}")
    assert client.get(f"{API}/health").json()["data_built_at"].endswith("+00:00")


def test_listing_sees_a_rebuild_without_restart(shared_client) -> None:
    client, _, (_, marts) = shared_client
    assert client.get(f"{API}/processes").json()["total"] == 5
    path = marts / "process_scores.parquet"
    pq.write_table(pq.read_table(path).slice(0, 3), path)
    assert client.get(f"{API}/processes").json()["total"] == 3
