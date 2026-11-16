"""Search of buying entities by name over an in-memory table built once per data build.

The table has one row per buyer RUC: the most frequent spelling of its name (ties: the smallest
name, as everywhere else), its most frequent province, and its number of processes. Natural-person
buyers (RUC third digit 0-5) and RUCs the API would reject (not 13 ASCII digits) are not in it, so
they cannot be found. Matching and ranking are plain string operations (`domain.text_match`): no
user text ever reaches SQL.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from veedor.domain.masking import COMPANY, PUBLIC_ENTITY, kind_from_ruc
from veedor.domain.regions import SIN_REGION, canonical_region, region_label
from veedor.domain.text_match import fold, match_rank
from veedor.use_cases.queries._cache import VersionedCache
from veedor.use_cases.queries.ports import LakePort

MAX_LIMIT = 10
_CACHE = VersionedCache(max_entries=2)

BUYER_TABLE_SQL = """
SELECT buyer_ruc, buyer_name, buyer_region, count(*) AS n
FROM processes
WHERE buyer_ruc IS NOT NULL AND buyer_name IS NOT NULL
GROUP BY buyer_ruc, buyer_name, buyer_region
"""


@dataclass(frozen=True, slots=True)
class BuyerEntry:
    ruc: str
    name: str
    folded: str
    region_label: str
    processes_total: int


def search_buyers(lake: LakePort, text: str, limit: int = MAX_LIMIT) -> dict[str, Any]:
    """Up to `limit` buyers whose name matches `text`, best match first, then most processes."""
    folded_query = fold(text)
    table: list[BuyerEntry] = _CACHE.get_or_compute("buyers", lake.data_version(), lambda: _build(lake))
    ranked: list[tuple[int, int, str, str, BuyerEntry]] = []
    for entry in table:
        rank = match_rank(entry.folded, folded_query)
        if rank is not None:
            ranked.append((rank, -entry.processes_total, entry.folded, entry.ruc, entry))
    ranked.sort(key=lambda item: item[:4])
    return {
        "items": [
            {
                "ruc": e.ruc,
                "name": e.name,
                "region_label": e.region_label,
                "processes_total": e.processes_total,
            }
            for *_, e in ranked[: max(1, min(limit, MAX_LIMIT))]
        ]
    }


def _build(lake: LakePort) -> list[BuyerEntry]:
    rows = lake.fetch(BUYER_TABLE_SQL, tables=("processes",))
    names: dict[str, Counter[str]] = {}
    regions: dict[str, Counter[str]] = {}
    for row in rows:
        ruc = str(row["buyer_ruc"])
        if len(ruc) != 13 or kind_from_ruc(ruc) not in (PUBLIC_ENTITY, COMPANY):
            continue
        count = int(row["n"])
        names.setdefault(ruc, Counter())[str(row["buyer_name"]).strip()] += count
        key = canonical_region(row["buyer_region"])
        if key is not None and key != SIN_REGION:
            regions.setdefault(ruc, Counter())[key] += count
    table = []
    for ruc, spellings in names.items():
        name = _most_frequent(spellings)
        if not name:
            continue
        region = _most_frequent(regions[ruc]) if ruc in regions else SIN_REGION
        table.append(BuyerEntry(ruc, name, fold(name), region_label(region), sum(spellings.values())))
    return table


def _most_frequent(counts: Counter[str]) -> str:
    """Highest count; ties go to the smallest value so every worker agrees."""
    return min(counts, key=lambda value: (-counts[value], value))
