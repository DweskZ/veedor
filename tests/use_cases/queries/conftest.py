from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures" / "api"))

from api_fixture_data import build_fixture_data  # noqa: E402

from veedor.infrastructure.lake.reader import LakeReader  # noqa: E402


@pytest.fixture
def lake(tmp_path: Path) -> LakeReader:
    return LakeReader(*build_fixture_data(tmp_path))
