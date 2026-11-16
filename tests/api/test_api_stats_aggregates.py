"""`/stats/by-region`, `/stats/by-year` and the `region` filter of `/processes`.

Every expected number is recomputed here, in plain Python, from the rows that built the fixture
lake, so the tests do not repeat the SQL they check.

Real-data reproduction (DuckDB over data/lake and data/marts; this is the query the endpoint runs):

    SELECT trim(p.buyer_region) AS region,
           count(*) FILTER (WHERE p.method_group = 'competitive') AS competitive,
           count(*) FILTER (WHERE p.method_group = 'competitive' AND s.n_signals > 0) AS with_signal
    FROM read_parquet('data/lake/processes.parquet') p
    LEFT JOIN read_parquet('data/marts/process_scores.parquet') s USING (ocid)
    GROUP BY 1 ORDER BY 1;

    -- 2015 and 2026 single-bidder share of reverse auctions
    SELECT year, avg((n_tenderers = 1)::INT) FROM read_parquet('data/lake/processes.parquet')
    WHERE method = 'Subasta Inversa Electrónica' AND n_tenderers IS NOT NULL GROUP BY year;
"""

from __future__ import annotations

import api_fixture_data as fx
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from veedor.domain.regions import REGION_LABELS, SIN_REGION, canonical_region, region_label
from veedor.use_cases.queries import year_stats

API = "/api/v1"


def _region_key(row: dict) -> str:
    return canonical_region(row["buyer_region"]) or SIN_REGION


def _expected_region(rows: list[dict]) -> dict:
    competitive = [r for r in rows if r["method_group"] == "competitive"]
    flagged = [r for r in competitive if r["signals"]]
    single = [r for r in competitive if "SINGLE_BIDDER" in r["signals"]]
    return {
        "competitive_processes": len(competitive),
        "with_signal": len(flagged),
        "single_bidder": len(single),
        "processes_total": len(rows),
        "awarded_total": round(sum(r["award_total"] or 0 for r in rows), 2),
        "mean_score": round(sum(r["score"] for r in competitive) / len(competitive), 2)
        if competitive
        else None,
    }


def test_by_region_matches_a_recomputation_per_province(stats_client: TestClient) -> None:
    body = stats_client.get(f"{API}/stats/by-region").json()
    rows = fx.stats_rows()
    by_key: dict[str, list[dict]] = {}
    for row in rows:
        by_key.setdefault(_region_key(row), []).append(row)
    assert {i["region"] for i in body["items"]} == set(by_key)
    for item in body["items"]:
        expected = _expected_region(by_key[item["region"]])
        for field, value in expected.items():
            assert item[field] == pytest.approx(value), (item["region"], field)
        if expected["competitive_processes"]:
            share = 100 * expected["with_signal"] / expected["competitive_processes"]
            assert item["pct_with_signal"] == pytest.approx(share, abs=0.006)
            single = 100 * expected["single_bidder"] / expected["competitive_processes"]
            assert item["pct_single_bidder"] == pytest.approx(single, abs=0.006)
        assert item["region_label"] == region_label(item["region"])
    assert body["basis"] == "competitive"


def test_raw_spellings_of_one_province_are_merged(stats_client: TestClient) -> None:
    items = {i["region"]: i for i in stats_client.get(f"{API}/stats/by-region").json()["items"]}
    assert "LOS RIOS" in items and not any(key.strip() != key for key in items)  # ' Los Ríos ' + 'LOS RIOS'
    assert items["LOS RIOS"]["region_label"] == "Los Ríos"
    assert items["CAÑAR"]["region_label"] == "Cañar"


def test_null_province_is_grouped_as_sin_region(stats_client: TestClient) -> None:
    items = {i["region"]: i for i in stats_client.get(f"{API}/stats/by-region").json()["items"]}
    assert items[SIN_REGION]["region_label"] == "Sin provincia registrada"
    assert items[SIN_REGION]["competitive_processes"] == len(
        fx.STATS_YEARS
    )  # one tender per year, no province
    assert [i["region"] for i in stats_client.get(f"{API}/stats/by-region").json()["items"]][-1] == SIN_REGION


def test_national_row_is_the_sum_of_the_rows(stats_client: TestClient) -> None:
    body = stats_client.get(f"{API}/stats/by-region").json()
    national, items = body["national"], body["items"]
    assert national["region"] == "NACIONAL" and national["region_label"] == "Nacional"
    for field in ("competitive_processes", "with_signal", "single_bidder", "processes_total"):
        assert national[field] == sum(i[field] for i in items)
    assert national["awarded_total"] == pytest.approx(sum(i["awarded_total"] for i in items))
    assert national["processes_total"] == len(fx.stats_rows())
    assert national["small_sample"] is False


def test_provinces_under_500_competitive_processes_are_flagged(stats_client: TestClient) -> None:
    body = stats_client.get(f"{API}/stats/by-region").json()
    assert body["items"] and all(i["small_sample"] is True for i in body["items"])  # fixture is tiny


def test_province_with_no_competitive_process_has_null_percentages(stats_client: TestClient) -> None:
    items = {i["region"]: i for i in stats_client.get(f"{API}/stats/by-region").json()["items"]}
    # AZUAY only has the Cotización of the Ñandú buyer; every province in the fixture has a tender, so
    # force the empty case through the pure rounding helper instead.
    assert items["AZUAY"]["competitive_processes"] == 2  # Ñandú + the buyer whose RUC is too short
    from veedor.use_cases.queries import region_stats

    assert region_stats._pct(0, 0) is None


def test_natural_person_buyer_still_counts_in_aggregates_but_is_never_named(stats_client: TestClient) -> None:
    text = stats_client.get(f"{API}/stats/by-region").text
    assert fx.NATURAL_BUYER_NAME not in text and fx.NATURAL_BUYER_RUC not in text


def test_region_aggregate_is_not_recomputed_per_request(stats_client: TestClient, monkeypatch) -> None:
    from veedor.api.deps import get_reader

    reader = stats_client.app.dependency_overrides[get_reader]()
    first = stats_client.get(f"{API}/stats/by-region").json()
    calls: list[str] = []
    real = reader.fetch
    monkeypatch.setattr(reader, "fetch", lambda sql, *a, **k: calls.append(sql) or real(sql, *a, **k))
    assert stats_client.get(f"{API}/stats/by-region").json() == first
    assert stats_client.get(f"{API}/stats/by-year").status_code == 200  # cold: runs its own queries
    calls.clear()
    stats_client.get(f"{API}/stats/by-year")
    stats_client.get(f"{API}/stats/by-region")
    assert calls == []


def test_by_region_cache_follows_a_rebuild(stats_client: TestClient, stats_dirs) -> None:
    before = stats_client.get(f"{API}/stats/by-region").json()["national"]["processes_total"]
    path = stats_dirs[0] / "processes.parquet"
    pq.write_table(pq.read_table(path).slice(0, 10), path)
    after = stats_client.get(f"{API}/stats/by-region").json()["national"]["processes_total"]
    assert (before, after) == (len(fx.stats_rows()), 10)


def test_by_region_503_when_the_lake_is_missing(empty_client: TestClient) -> None:
    response = empty_client.get(f"{API}/stats/by-region")
    assert response.status_code == 503 and response.json()["error"]["code"] == "data_unavailable"


# --- by-year


def _single_bidder_share(rows: list[dict], year: int) -> tuple[int, int]:
    auctions = [
        r for r in rows if r["year"] == year and r["method"] == fx.SIE and r["n_tenderers"] is not None
    ]
    return sum(1 for r in auctions if r["n_tenderers"] == 1), len(auctions)


def test_by_year_matches_a_recomputation(stats_client: TestClient) -> None:
    body = stats_client.get(f"{API}/stats/by-year").json()
    rows = fx.stats_rows()
    assert [i["year"] for i in body["items"]] == list(fx.STATS_YEARS)
    assert body["single_bidder_method"] == fx.SIE
    for item in body["items"]:
        year_rows = [r for r in rows if r["year"] == item["year"]]
        competitive = [r for r in year_rows if r["method_group"] == "competitive"]
        single, known = _single_bidder_share(rows, item["year"])
        assert item["processes_total"] == len(year_rows)
        assert item["competitive_processes"] == len(competitive)
        assert (item["single_bidder_count"], item["single_bidder_base"]) == (single, known)
        assert item["pct_single_bidder"] == pytest.approx(100 * single / known, abs=0.006)
        flagged = sum(1 for r in competitive if r["signals"])
        assert item["pct_with_signal"] == pytest.approx(100 * flagged / len(competitive), abs=0.006)
        assert item["awarded_total"] == pytest.approx(sum(r["award_total"] or 0 for r in year_rows))


def test_method_mix_uses_awarded_amounts_and_skips_null_amounts(stats_client: TestClient) -> None:
    body = stats_client.get(f"{API}/stats/by-year").json()
    rows = fx.stats_rows()
    item = next(i for i in body["items"] if i["year"] == 2024)  # has a reverse auction with no amount
    amounts = {"competitive": 0.0, "direct": 0.0, "catalogue": 0.0}
    for row in rows:
        if row["year"] == 2024 and row["award_total"] is not None:
            amounts[row["method_group"]] += row["award_total"]
    total = sum(amounts.values())
    for group, amount in amounts.items():
        assert item["method_mix"][group] == pytest.approx(100 * amount / total, abs=0.006)
    assert sum(v for v in item["method_mix"].values() if v is not None) == pytest.approx(100, abs=0.02)


def test_by_year_flags_the_last_year_and_carries_the_spanish_notes(stats_client: TestClient) -> None:
    body = stats_client.get(f"{API}/stats/by-year").json()
    flags = {i["year"]: i["partial_year"] for i in body["items"]}
    assert flags == {2021: False, 2022: False, 2023: False, 2024: False, 2025: True}
    by_year = {i["year"]: i["notes"] for i in body["items"]}
    assert by_year[2022] == [year_stats.NOTE_2022] and by_year[2021] == [] and by_year[2023] == []
    assert year_stats.NOTE_NAMING in by_year[2025] and year_stats.NOTE_PARTIAL in by_year[2025]
    assert year_stats.NOTE_2022 in body["notes"] and year_stats.NOTE_NAMING in body["notes"]
    assert all(isinstance(note, str) for note in body["notes"])


def test_a_year_that_ends_in_december_is_not_partial() -> None:
    counters = ("processes_total", "competitive_processes", "single_bidder_base", "single_bidder_count")
    amounts = ("awarded_total", "amount_competitive", "amount_direct", "amount_catalogue", "amount_other")
    row = {"year": 2025, "with_signal": 0, **dict.fromkeys(counters, 0), **dict.fromkeys(amounts, 0)}
    assert year_stats._item(row, 2025, "2025-12-31")["partial_year"] is False
    assert year_stats._item(row, 2025, "2025-11-16")["partial_year"] is True
    assert year_stats._item(row, 2026, "2025-11-16")["partial_year"] is False
    item = year_stats._item(row, 2025, "2025-12-31")
    assert item["pct_single_bidder"] is None and item["method_mix"]["direct"] is None


# --- region filter on /processes


def _ids(client: TestClient, **params) -> set[str]:
    out, page = set(), 1
    while True:
        body = client.get(f"{API}/processes", params={**params, "page": page, "page_size": 100}).json()
        out |= {i["ocid"] for i in body["items"]}
        if len(out) >= body["total"]:
            return out
        page += 1


def test_region_filter_selects_the_provinces_processes(stats_client: TestClient) -> None:
    rows = fx.stats_rows()
    for key in ("MANABI", "LOS RIOS", "CAÑAR", "PICHINCHA", "AZUAY"):
        expected = {r["ocid"] for r in rows if _region_key(r) == key}
        assert _ids(stats_client, region=key) == expected, key


def test_sin_region_selects_rows_without_a_province(stats_client: TestClient) -> None:
    expected = {r["ocid"] for r in fx.stats_rows() if r["buyer_region"] is None}
    assert expected and _ids(stats_client, region="SIN_REGION") == expected


def test_region_works_with_other_filters_and_sorting(stats_client: TestClient) -> None:
    rows = fx.stats_rows()
    expected = [
        r
        for r in rows
        if _region_key(r) == "MANABI" and r["year"] == 2023 and "SINGLE_BIDDER" in r["signals"]
    ]
    body = stats_client.get(
        f"{API}/processes",
        params={"region": "MANABI", "year": 2023, "signal": "SINGLE_BIDDER", "sort": "-award_total"},
    ).json()
    assert body["total"] == len(expected) > 0
    amounts = [i["award_total"] for i in body["items"]]
    assert amounts == sorted(amounts, reverse=True)
    both = stats_client.get(f"{API}/processes", params={"region": "MANABI", "q": "ST-0001"}).json()
    assert both["total"] == 1


def test_region_filter_total_matches_the_by_region_row(stats_client: TestClient) -> None:
    items = {i["region"]: i for i in stats_client.get(f"{API}/stats/by-region").json()["items"]}
    for key, item in items.items():
        total = stats_client.get(f"{API}/processes", params={"region": key, "page_size": 1}).json()["total"]
        assert total == item["processes_total"], key


@pytest.mark.parametrize("value", ["manabi", "Manabí", "ATLANTIDA", "", "MANABI;", "%", "los rios"])
def test_unknown_region_is_422(stats_client: TestClient, value: str) -> None:
    response = stats_client.get(f"{API}/processes", params={"region": value})
    assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"


def test_every_documented_region_key_is_accepted(stats_client: TestClient) -> None:
    for key in (*REGION_LABELS, SIN_REGION):
        assert stats_client.get(f"{API}/processes", params={"region": key, "page_size": 1}).status_code == 200


def test_region_filter_needs_the_processes_table(client: TestClient, lake_dirs) -> None:
    (lake_dirs[0] / "processes.parquet").unlink()
    response = client.get(f"{API}/processes", params={"region": "MANABI"})
    assert response.status_code == 503
