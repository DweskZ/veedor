"""LakeReader reuses one locked-down database, refreshes it after a rebuild and stays locked."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures" / "api"))

from api_fixture_data import build_fixture_data  # noqa: E402

from veedor.infrastructure.lake.reader import LakeReader  # noqa: E402
from veedor.use_cases.queries import stats  # noqa: E402

COUNT_SCORES = "SELECT count(*) AS n FROM process_scores"


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    return build_fixture_data(tmp_path)


@pytest.fixture
def reader(dirs: tuple[Path, Path]) -> LakeReader:
    return LakeReader(*dirs, refresh_interval=0)


def _shrink_scores(marts: Path, keep: int) -> None:
    path = marts / "process_scores.parquet"
    pq.write_table(pq.read_table(path).slice(0, keep), path)


def test_database_is_built_once_and_reused(dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    reader = LakeReader(*dirs, refresh_interval=3600)
    builds = []
    real = reader._build
    monkeypatch.setattr(reader, "_build", lambda: builds.append(1) or real())
    for _ in range(5):
        assert reader.fetch(COUNT_SCORES, tables=("process_scores",))[0]["n"] == 5
    assert len(builds) == 1


def test_threads_are_bounded(dirs) -> None:
    reader = LakeReader(*dirs, threads=3)
    rows = reader.fetch("SELECT current_setting('threads') AS t", tables=("process_scores",))
    assert int(rows[0]["t"]) == 3


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM read_text('/etc/hosts')",
        "SELECT * FROM read_csv('/etc/passwd')",
        "COPY (SELECT 1) TO '/tmp/veedor_lockdown_probe.csv'",
        "ATTACH '/tmp/veedor_lockdown_probe.db' AS probe",
        "INSTALL httpfs",
        "LOAD httpfs",
        "SET enable_external_access=true",
        "SET allowed_directories=['/']",
        "SET lock_configuration=false",
        "SELECT * FROM read_parquet('/etc/hosts')",
    ],
)
def test_lockdown_holds_on_the_reused_database_from_every_cursor(reader: LakeReader, statement: str) -> None:
    reader.fetch(COUNT_SCORES, tables=("process_scores",))  # database now exists and is shared
    database = reader._current(("process_scores",))
    for cursor in (database.cursor(), database.cursor()):  # two independent cursors
        with pytest.raises(duckdb.Error):
            cursor.execute(statement)
        cursor.close()
    assert not Path("/tmp/veedor_lockdown_probe.csv").exists()


@pytest.mark.parametrize(
    "statement",
    [
        "DROP VIEW process_scores",
        "SELECT 1; CREATE TABLE leak AS SELECT 1",
        "SELECT 1; CREATE OR REPLACE VIEW process_scores AS SELECT 1 AS ocid",
        "WITH x AS (SELECT 1) INSERT INTO leak SELECT * FROM x",
        "SELECT 1; SET enable_external_access=true",
        "EXPLAIN SELECT 1",
    ],
)
def test_only_a_single_select_reaches_the_shared_database(reader: LakeReader, statement: str) -> None:
    with pytest.raises(ValueError):
        reader.fetch(statement, tables=("process_scores",))
    assert reader.fetch(COUNT_SCORES, tables=("process_scores",))[0]["n"] == 5  # nothing persisted


def test_replaced_marts_are_picked_up(dirs) -> None:
    _, marts = dirs
    reader = LakeReader(*dirs, refresh_interval=0)
    assert reader.fetch(COUNT_SCORES, tables=("process_scores",))[0]["n"] == 5
    before = reader.data_version()
    _shrink_scores(marts, 2)
    assert reader.fetch(COUNT_SCORES, tables=("process_scores",))[0]["n"] == 2
    assert reader.data_version() != before


def test_a_file_that_appears_later_is_registered(tmp_path: Path) -> None:
    lake, marts = tmp_path / "lake", tmp_path / "marts"
    reader = LakeReader(lake, marts, refresh_interval=3600)
    build_fixture_data(tmp_path)
    assert reader.fetch(COUNT_SCORES, tables=("process_scores",))[0]["n"] == 5


def test_built_at_follows_the_build_summary(dirs) -> None:
    _, marts = dirs
    reader = LakeReader(*dirs)
    assert reader.built_at() is None
    (marts / "build_summary.json").write_text("{}")
    assert reader.built_at() is not None
    first = reader.data_version()
    (marts / "build_summary.json").write_text('{"rebuilt": true}')
    assert reader.data_version() != first


def test_concurrent_cursors_return_consistent_rows(reader: LakeReader) -> None:
    failures: list[str] = []

    def work() -> None:
        for _ in range(25):
            rows = reader.fetch("SELECT ocid FROM process_scores ORDER BY ocid", tables=("process_scores",))
            if len(rows) != 5:
                failures.append(f"got {len(rows)} rows")

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == []


def test_stats_are_cached_until_the_data_changes(dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    _, marts = dirs
    reader = LakeReader(*dirs, refresh_interval=0)
    monkeypatch.setattr(stats, "_cached", None)
    calls = []
    real = reader.fetch
    monkeypatch.setattr(reader, "fetch", lambda *a, **k: calls.append(1) or real(*a, **k))
    first = stats.get_stats_cached(reader)
    used = len(calls)
    assert used > 0
    assert stats.get_stats_cached(reader) == first
    assert len(calls) == used  # second call served from memory
    _shrink_scores(marts, 2)
    refreshed = stats.get_stats_cached(reader)
    assert refreshed["processes_scored"] == 2 != first["processes_scored"]
    assert len(calls) > used
