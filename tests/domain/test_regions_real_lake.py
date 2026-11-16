"""Every `buyer_region` value of the real lake maps to a known province label.

Skipped where the lake is not built (CI, fresh clones): the other tests never need it. Only the list
of distinct region values is read.
"""

from __future__ import annotations

import duckdb
import pytest

from veedor.core.settings import get_settings
from veedor.domain.regions import PROVINCE_KEYS, canonical_region, region_label

LAKE_FILE = get_settings().lake_dir / "processes.parquet"


@pytest.mark.skipif(not LAKE_FILE.is_file(), reason="data/lake/processes.parquet is not built")
def test_every_region_value_in_the_lake_has_a_label() -> None:
    connection = duckdb.connect(":memory:")
    try:
        values = [
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT buyer_region FROM read_parquet(?) WHERE buyer_region IS NOT NULL",
                [str(LAKE_FILE)],
            ).fetchall()
        ]
    finally:
        connection.close()
    assert values, "the lake has no region values at all"
    unmapped = [value for value in values if canonical_region(value) not in PROVINCE_KEYS]
    assert unmapped == []
    assert all(region_label(canonical_region(value)) for value in values)  # type: ignore[arg-type]
    assert all(value == canonical_region(value) for value in values), "raw values are already canonical"
