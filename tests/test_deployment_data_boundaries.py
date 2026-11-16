"""The unmasked process texts must stay out of everything that is mounted into or published from the API."""

from __future__ import annotations

import re
from pathlib import Path

from veedor.core.settings import REPO_ROOT, Settings
from veedor.infrastructure.lake.reader import LAKE_TABLES, MART_TABLES


def test_texts_live_outside_the_lake_and_marts_folders():
    settings = Settings(data_dir=Path("/srv/veedor/data"))
    assert settings.texts_dir == Path("/srv/veedor/data/texts")
    for mounted in (settings.lake_dir, settings.marts_dir):
        assert mounted not in settings.texts_dir.parents and settings.texts_dir != mounted


def test_the_api_reader_cannot_see_the_texts_table():
    assert "process_texts" not in LAKE_TABLES + MART_TABLES


def test_compose_does_not_mount_the_texts_or_the_whole_data_folder_into_the_api():
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    mounts = re.findall(r"^\s*-\s+(\S+:\S+)\s*$", compose, flags=re.MULTILINE)
    host_sources = [m.split(":")[0] for m in mounts if m.startswith(("./", "/"))]
    assert "./data/lake" in host_sources and "./data/marts" in host_sources
    assert not [m for m in mounts if "texts" in m.split(":")[0] or "process_texts" in m]
    assert "./data" not in host_sources and "./data/" not in host_sources


def test_the_data_bundle_does_not_ship_the_texts():
    script = (REPO_ROOT / "scripts" / "build_data_bundle.sh").read_text(encoding="utf-8")
    tables = re.findall(r"^(?:LAKE|MART)_TABLES=\(([^)]*)\)", script, flags=re.MULTILINE)
    assert tables and all("process_texts" not in t for t in tables)
    assert "process_quotes" in script and "process_quote_stats" in script
