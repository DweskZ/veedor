"""`/processes/random`, `/buyers/search` and `/processes/{ocid}/context` over the statistics fixture."""

from __future__ import annotations

from collections import Counter

import api_fixture_data as fx
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from veedor.use_cases.queries import random_process

API = "/api/v1"
PERSON_TOKENS = (fx.NATURAL_NAME, fx.NATURAL_RUC, fx.NORUC_NAME, fx.NATURAL_BUYER_NAME, fx.NATURAL_BUYER_RUC)


def _eligible(rows: list[dict], signals: bool | None = None, min_score: float | None = None) -> set[str]:
    out = set()
    for row in rows:
        ruc = row["winner"][0]
        if not ruc or row["winner"][2] not in {"company", "public_entity"}:
            continue
        if row["buyer_ruc"] == fx.NATURAL_BUYER_RUC:
            continue
        if signals is not None and bool(row["signals"]) != signals:
            continue
        if min_score is not None and row["score"] < min_score:
            continue
        out.add(row["ocid"])
    return out


def _draw(client: TestClient, times: int, **params) -> list[dict]:
    responses = [client.get(f"{API}/processes/random", params=params) for _ in range(times)]
    assert {r.status_code for r in responses} == {200}
    return [r.json() for r in responses]


# --- random


def test_random_returns_a_list_item_shape_and_is_never_cached(stats_client: TestClient) -> None:
    response = stats_client.get(f"{API}/processes/random")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    listed = stats_client.get(f"{API}/processes", params={"page_size": 1}).json()["items"][0]
    assert set(response.json()) == set(listed)


def test_random_only_returns_company_or_public_entity_winners(stats_client: TestClient) -> None:
    allowed = _eligible(fx.stats_rows())
    for body in _draw(stats_client, 150):
        assert body["ocid"] in allowed
        assert body["winner_kind"] in {"company", "public_entity"} and body["winner_ruc"]


def test_random_never_names_natural_persons_or_unidentified_winners(stats_client: TestClient) -> None:
    people = {r["ocid"] for r in fx.stats_rows() if r["winner"][2] in {"natural_person", None}}
    people |= {r["ocid"] for r in fx.stats_rows() if r["buyer_ruc"] == fx.NATURAL_BUYER_RUC}
    assert people
    texts = []
    for _ in range(200):
        response = stats_client.get(f"{API}/processes/random")
        assert response.json()["ocid"] not in people
        texts.append(response.text)
    joined = "\n".join(texts)
    assert not any(token in joined for token in PERSON_TOKENS)


def test_with_signals_true_and_false_split_the_candidates(stats_client: TestClient) -> None:
    rows = fx.stats_rows()
    for flag in (True, False):
        allowed = _eligible(rows, signals=flag)
        assert allowed
        for body in _draw(stats_client, 60, with_signals=str(flag).lower()):
            assert body["ocid"] in allowed and (body["n_signals"] > 0) is flag


def test_min_score_is_applied_exactly(stats_client: TestClient) -> None:
    rows = fx.stats_rows()
    assert all(r["score"] in (0.0, 30.0, 60.0) for r in rows)
    allowed = _eligible(rows, min_score=30.0)
    for body in _draw(stats_client, 40, min_score=30):
        assert body["ocid"] in allowed and body["risk_score"] >= 30
    for body in _draw(stats_client, 20, min_score=30.5):  # floors to 30, exact threshold keeps the 60s
        assert body["risk_score"] == 60.0
    assert stats_client.get(f"{API}/processes/random", params={"min_score": 60.5}).status_code == 404
    assert stats_client.get(f"{API}/processes/random", params={"min_score": 100}).status_code == 404


def test_no_match_is_a_404_and_is_not_rescanned_in_a_burst(stats_client: TestClient, monkeypatch) -> None:
    from veedor.api.deps import get_reader

    reader = stats_client.app.dependency_overrides[get_reader]()
    assert stats_client.get(f"{API}/processes/random", params={"min_score": 99}).status_code == 404
    calls = []
    real = reader.fetch
    monkeypatch.setattr(reader, "fetch", lambda sql, *a, **k: calls.append(sql) or real(sql, *a, **k))
    for _ in range(20):
        response = stats_client.get(f"{API}/processes/random", params={"min_score": 99})
        assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
    assert calls == []


def test_draws_cover_every_candidate_and_do_not_repeat_within_a_pool(stats_client: TestClient) -> None:
    candidates = _eligible(fx.stats_rows(), signals=True)
    first_round = [b["ocid"] for b in _draw(stats_client, len(candidates), with_signals="true")]
    assert len(set(first_round)) == len(candidates) == len(first_round)  # without replacement, all seen
    later = Counter(b["ocid"] for b in _draw(stats_client, 10 * len(candidates), with_signals="true"))
    assert set(later) == candidates
    assert min(later.values()) == max(later.values()) == 10  # whole set re-served each cycle: uniform


def test_choice_is_uniform_over_a_larger_pool(stats_client: TestClient) -> None:
    candidates = _eligible(fx.stats_rows())
    n = len(candidates)
    draws = Counter(b["ocid"] for b in _draw(stats_client, 20 * n))
    assert set(draws) == candidates
    assert min(draws.values()) == max(draws.values()) == 20  # complete pools are served cyclically


def test_warm_draws_do_no_database_work(stats_client: TestClient, monkeypatch) -> None:
    from veedor.api.deps import get_reader

    reader = stats_client.app.dependency_overrides[get_reader]()
    stats_client.get(f"{API}/processes/random")
    calls = []
    real = reader.fetch
    monkeypatch.setattr(reader, "fetch", lambda sql, *a, **k: calls.append(sql) or real(sql, *a, **k))
    for _ in range(5):
        stats_client.get(f"{API}/processes/random")
    assert calls == []


def test_large_match_sets_are_sampled_not_listed(stats_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(random_process, "POOL_SIZE", 5)
    random_process._POOLS.clear()
    seen = {b["ocid"] for b in _draw(stats_client, 60)}
    assert len(seen) > 5  # several independent samples of 5, each served without replacement
    assert seen <= _eligible(fx.stats_rows())


def test_random_pool_follows_a_rebuild(stats_client: TestClient, stats_dirs) -> None:
    assert stats_client.get(f"{API}/processes/random").status_code == 200
    path = stats_dirs[1] / "process_scores.parquet"
    table = pq.read_table(path)
    keep = table.filter(
        table["ocid"].to_pylist() and [o == "ocds-5wno2w-st-0001" for o in table["ocid"].to_pylist()]
    )
    pq.write_table(keep, path)
    assert {b["ocid"] for b in _draw(stats_client, 5)} == {"ocds-5wno2w-st-0001"}


def test_random_route_is_not_shadowed_by_the_process_detail(stats_client: TestClient) -> None:
    response = stats_client.get(f"{API}/processes/random")  # the detail route would answer 422 here
    assert response.status_code == 200 and response.json()["ocid"].startswith("ocds-5wno2w-st-")


@pytest.mark.parametrize(
    "params", [{"with_signals": "maybe"}, {"min_score": "abc"}, {"min_score": 101}, {"min_score": -1}]
)
def test_random_rejects_invalid_parameters(stats_client: TestClient, params: dict) -> None:
    assert stats_client.get(f"{API}/processes/random", params=params).status_code == 422


# --- buyer search


def _search(client: TestClient, q: str, **params):
    return client.get(f"{API}/buyers/search", params={"q": q, **params})


def test_search_is_accent_and_case_insensitive(stats_client: TestClient) -> None:
    for q in ("nandu", "ÑANDÚ", "Gobierno Municipal Ñandú", "  nandú  "):
        items = _search(stats_client, q).json()["items"]
        assert [i["name"] for i in items] == ["Gobierno Municipal Ñandú"], q
    assert _search(stats_client, "PUBLICA ficticia").json()["items"][0]["ruc"] == "1760002340001"


def test_search_ranks_prefix_then_word_start_then_substring_then_volume(stats_client: TestClient) -> None:
    items = _search(stats_client, "mun").json()["items"]
    names = [i["name"] for i in items]
    # prefix: both spellings of one buyer are one row ("MUNICIPIO DE EJEMPLO SUR"); word start next.
    assert names[0] == "MUNICIPIO DE EJEMPLO SUR"
    assert names[1:] == ["GAD Municipal de Ejemplo", "Gobierno Municipal Ñandú"]


def test_search_substring_matches_come_last_ordered_by_volume(stats_client: TestClient) -> None:
    items = _search(stats_client, "ipal").json()["items"]  # inside "municipal", never at a word start
    assert [i["name"] for i in items] == ["GAD Municipal de Ejemplo", "Gobierno Municipal Ñandú"]
    assert items[0]["processes_total"] > items[1]["processes_total"]


def test_word_start_matches_are_ordered_by_number_of_processes(stats_client: TestClient) -> None:
    items = _search(stats_client, "ejemplo").json()["items"]
    assert {i["name"] for i in items} == {
        "GAD Municipal de Ejemplo",
        "MUNICIPIO DE EJEMPLO SUR",
        "Hospital Ejemplo Norte",
        "Universidad Ejemplo del Cañar",
    }
    totals = [i["processes_total"] for i in items]
    assert totals == sorted(totals, reverse=True)


def test_most_frequent_spelling_and_total_per_ruc(stats_client: TestClient) -> None:
    (hit,) = [i for i in _search(stats_client, "ejemplo sur").json()["items"] if i["ruc"] == "1760006780001"]
    rows = [r for r in fx.stats_rows() if r["buyer_ruc"] == "1760006780001"]
    names = Counter(r["buyer_name"] for r in rows)
    assert hit["name"] == names.most_common(1)[0][0]
    assert hit["processes_total"] == len(rows)
    assert hit["region_label"] == "Pichincha"


def test_buyer_without_province_gets_the_placeholder_label(stats_client: TestClient) -> None:
    (hit,) = _search(stats_client, "ministerio de prueba").json()["items"]
    assert hit["region_label"] == "Sin provincia registrada"


def test_natural_person_buyers_and_invalid_rucs_are_not_searchable(stats_client: TestClient) -> None:
    for q in ("compradora", "Rosa Compradora Ejemplo", "1712000000001", "ruc corto", "Municipio Con Ruc"):
        response = _search(stats_client, q)
        assert response.status_code == 200 and response.json()["items"] == [], q
    assert fx.NATURAL_BUYER_NAME not in _search(stats_client, "ejemplo").text


def test_search_excludes_winners_and_descriptions(stats_client: TestClient) -> None:
    for q in (fx.NATURAL_NAME, "Constructora", "insumos"):
        assert _search(stats_client, q).json()["items"] == []


def test_limit_is_bounded(stats_client: TestClient) -> None:
    assert len(_search(stats_client, "ejemplo", limit=2).json()["items"]) == 2
    assert len(_search(stats_client, "ejemplo").json()["items"]) <= 10
    for limit in (0, 11, -1, "x", "1;DROP"):
        assert _search(stats_client, "ejemplo", limit=limit).status_code == 422


@pytest.mark.parametrize("q", ["ab", "   ab  ", "", "   ", "x" * 61, "\x00abc", "ab\tc", "a​bc", "a‮bc"])
def test_search_text_validation(stats_client: TestClient, q: str) -> None:
    assert _search(stats_client, q).status_code == 422


def test_search_text_edges_are_accepted(stats_client: TestClient) -> None:
    assert _search(stats_client, "abc").status_code == 200
    assert _search(stats_client, "x" * 60).status_code == 200
    assert _search(stats_client, "  " + "x" * 60 + "  ").status_code == 200  # trimmed before the length check
    assert stats_client.get(f"{API}/buyers/search").status_code == 422


@pytest.mark.parametrize("q", ["%%%", "___", "\\\\\\", "' OR 1=1 --", "1; DROP TABLE x", "%00%"])
def test_wildcards_and_sql_are_plain_text(stats_client: TestClient, q: str) -> None:
    response = _search(stats_client, q)
    assert response.status_code == 200 and response.json()["items"] == []


def test_like_wildcards_are_separators_not_patterns(stats_client: TestClient) -> None:
    """`%` and `_` never widen a match: they are dropped like any other punctuation."""
    plain = _search(stats_client, "mun").json()
    assert _search(stats_client, "mun%").json() == plain == _search(stats_client, "mun_").json()
    assert _search(stats_client, "m%n%").json()["items"] == _search(stats_client, "m n").json()["items"]
    assert _search(stats_client, "%%%mun").json() == plain
    assert _search(stats_client, "xyz%").json()["items"] == []


def test_search_table_is_built_once_per_data_build(stats_client: TestClient, monkeypatch, stats_dirs) -> None:
    from veedor.api.deps import get_reader

    reader = stats_client.app.dependency_overrides[get_reader]()
    assert _search(stats_client, "municip").status_code == 200
    calls = []
    real = reader.fetch
    monkeypatch.setattr(reader, "fetch", lambda sql, *a, **k: calls.append(sql) or real(sql, *a, **k))
    for q in ("municip", "hospital", "universidad"):
        assert _search(stats_client, q).status_code == 200
    assert calls == []
    path = stats_dirs[0] / "processes.parquet"
    table = pq.read_table(path)
    pq.write_table(
        table.filter([n != "Hospital Ejemplo Norte" for n in table["buyer_name"].to_pylist()]), path
    )
    monkeypatch.undo()
    assert _search(stats_client, "hospital").json()["items"] == []


def test_buyer_search_route_is_not_shadowed_by_the_detail_route(stats_client: TestClient) -> None:
    assert _search(stats_client, "municip").status_code == 200
    assert stats_client.get(f"{API}/buyers/search/").status_code in {404, 422}


# --- context


def _ocid(method: str, year: int, n_tenderers: int | None = None, buyer: str | None = None) -> str:
    for row in fx.stats_rows():
        if (
            row["method"] == method
            and row["year"] == year
            and (n_tenderers is None or row["n_tenderers"] == n_tenderers)
        ):
            if buyer is None or row["buyer_ruc"] == fx.STATS_BUYERS[buyer][0]:
                return row["ocid"]
    raise AssertionError("fixture row not found")


def _group(method: str, year: int) -> list[dict]:
    return [r for r in fx.stats_rows() if r["method"] == method and r["year"] == year]


def test_context_tenderer_distribution_and_percentile(stats_client: TestClient) -> None:
    ocid = _ocid(fx.SIE, 2023, n_tenderers=3)
    body = stats_client.get(f"{API}/processes/{ocid}/context").json()
    group = _group(fx.SIE, 2023)
    counts = Counter(min(r["n_tenderers"], 6) for r in group)
    assert body["method"] == fx.SIE and body["year"] == 2023 and body["comparable_processes"] == len(group)
    tenderers = body["tenderers"]
    assert [b["bucket"] for b in tenderers["distribution"]] == ["1", "2", "3", "4", "5", "6+"]
    assert [b["count"] for b in tenderers["distribution"]] == [counts.get(n, 0) for n in range(1, 7)]
    assert tenderers["value"] == 3 and tenderers["n"] == len(group)
    assert tenderers["percentile"] == pytest.approx(
        100 * sum(1 for r in group if r["n_tenderers"] <= 3) / len(group), abs=0.06
    )
    assert tenderers["reason_code"] is None and tenderers["reason"] is None


def test_context_ratio_quartiles_and_percentile(stats_client: TestClient) -> None:
    import statistics

    ocid = _ocid(fx.SIE, 2023, n_tenderers=2)
    ratio = stats_client.get(f"{API}/processes/{ocid}/context").json()["award_budget_ratio"]
    values = sorted(
        r["award_total"] / r["budget"] for r in _group(fx.SIE, 2023) if r["award_total"] and r["budget"]
    )
    q1, median, q3 = statistics.quantiles(values, n=4, method="inclusive")
    assert ratio["n"] == len(values)
    assert (ratio["q1"], ratio["median"], ratio["q3"]) == pytest.approx((q1, median, q3), abs=1e-4)
    mine = next(r for r in _group(fx.SIE, 2023) if r["ocid"] == ocid)
    assert ratio["value"] == pytest.approx(mine["award_total"] / mine["budget"], abs=1e-4)
    below = sum(1 for v in values if v <= mine["award_total"] / mine["budget"])
    assert ratio["percentile"] == pytest.approx(100 * below / len(values), abs=0.06)


def test_context_window_is_null_with_a_reason_for_reverse_auctions(stats_client: TestClient) -> None:
    window = stats_client.get(f"{API}/processes/{_ocid(fx.SIE, 2023)}/context").json()["tender_window_days"]
    assert window["value"] is None and window["median"] is None and window["n"] == 0
    assert window["reason_code"] == "not_published_for_procedure"
    assert window["reason"] == "Este tipo de procedimiento no publica este dato."


def test_context_window_for_tenders(stats_client: TestClient) -> None:
    ocid = _ocid("Licitación", 2023, buyer="pichincha")
    window = stats_client.get(f"{API}/processes/{ocid}/context").json()["tender_window_days"]
    days = sorted(
        r["tender_end"] and (int(r["tender_end"][8:10]) - int(r["tender_start"][8:10]))
        for r in _group("Licitación", 2023)
    )
    assert window["n"] == 5 and window["value"] == 9.0 and window["median"] == float(days[2])
    assert window["percentile"] == 80.0 and window["reason_code"] is None


def test_context_field_missing_for_this_process_only(stats_client: TestClient) -> None:
    ocid = _ocid(fx.SIE, 2024, n_tenderers=8)  # the 2024 reverse auction with no award amount
    row = next(
        r for r in fx.stats_rows() if r["year"] == 2024 and r["method"] == fx.SIE and r["award_total"] is None
    )
    body = stats_client.get(f"{API}/processes/{row['ocid']}/context").json()
    ratio = body["award_budget_ratio"]
    assert (
        ratio["value"] is None
        and ratio["percentile"] is None
        and ratio["n"] > 0
        and ratio["median"] is not None
    )
    assert ratio["reason_code"] == "not_available_for_process" and ratio["reason"]
    assert ocid


def test_context_for_catalogue_has_no_tenderers(stats_client: TestClient) -> None:
    body = stats_client.get(
        f"{API}/processes/{_ocid('Catálogo electrónico - Mejor oferta', 2021)}/context"
    ).json()
    assert body["tenderers"]["distribution"] == [] and body["tenderers"]["value"] is None
    assert body["tenderers"]["reason_code"] == "not_published_for_procedure"
    assert body["award_budget_ratio"]["median"] == 1.0


def test_context_compares_within_method_and_year_only(stats_client: TestClient) -> None:
    a = stats_client.get(f"{API}/processes/{_ocid(fx.SIE, 2021)}/context").json()
    b = stats_client.get(f"{API}/processes/{_ocid('Licitación', 2021)}/context").json()
    assert a["comparable_processes"] == len(_group(fx.SIE, 2021)) != b["comparable_processes"]


def test_context_groups_are_cached_per_method_and_year(stats_client: TestClient, monkeypatch) -> None:
    from veedor.api.deps import get_reader

    reader = stats_client.app.dependency_overrides[get_reader]()
    first, second = (r["ocid"] for r in _group(fx.SIE, 2022)[:2])
    stats_client.get(f"{API}/processes/{first}/context")
    calls = []
    real = reader.fetch
    monkeypatch.setattr(reader, "fetch", lambda sql, *a, **k: calls.append(sql) or real(sql, *a, **k))
    assert stats_client.get(f"{API}/processes/{second}/context").status_code == 200
    assert len(calls) == 1 and "FROM processes WHERE ocid = ?" in calls[0]  # only the process row


def test_context_has_nothing_personal(stats_client: TestClient) -> None:
    people = [
        r
        for r in fx.stats_rows()
        if r["winner"][2] in {"natural_person", None} or r["buyer_ruc"] == fx.NATURAL_BUYER_RUC
    ]
    assert people
    for row in people:
        response = stats_client.get(f"{API}/processes/{row['ocid']}/context")
        assert response.status_code == 200
        assert not any(token in response.text for token in PERSON_TOKENS)
        assert set(response.json()) == {
            "ocid",
            "method",
            "year",
            "comparable_processes",
            "tenderers",
            "award_budget_ratio",
            "tender_window_days",
        }


def test_context_for_unknown_process_is_404(stats_client: TestClient) -> None:
    assert stats_client.get(f"{API}/processes/ocds-5wno2w-missing/context").status_code == 404
    assert stats_client.get(f"{API}/processes/bad id/context").status_code == 422


def test_context_cache_follows_a_rebuild(stats_client: TestClient, stats_dirs) -> None:
    ocid = _ocid(fx.SIE, 2023)
    before = stats_client.get(f"{API}/processes/{ocid}/context").json()["comparable_processes"]
    path = stats_dirs[0] / "processes.parquet"
    table = pq.read_table(path)
    mask = [
        o == ocid or m != fx.SIE
        for o, m in zip(table["ocid"].to_pylist(), table["method"].to_pylist(), strict=True)
    ]
    pq.write_table(table.filter(mask), path)
    after = stats_client.get(f"{API}/processes/{ocid}/context").json()["comparable_processes"]
    assert before > 1 and after == 1
