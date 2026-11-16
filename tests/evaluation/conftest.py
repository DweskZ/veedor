from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures" / "evaluation"))

import synthetic_marts  # noqa: E402


@pytest.fixture(scope="session")
def synthetic_dirs(tmp_path_factory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("eval")
    lake, marts = root / "lake", root / "marts"
    synthetic_marts.build(lake, marts)
    return lake, marts
