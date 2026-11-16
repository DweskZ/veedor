#!/usr/bin/env python3
"""Small closed-loop load test for the API (standard library only).

    uv run python scripts/load_test.py --requests 600 --concurrency 8 [--json-only]

Sends a fixed, deterministic mix of routes (stats, filtered and sorted lists, detail, dossier,
similar, a 404 and a 422) from `--concurrency` threads, each on its own keep-alive connection,
and reports p50/p95/p99/max latency per route and overall, status counts and requests/second.
The route mix is the same for every run, so two runs are comparable.

Notes: the dossier route is rate limited by the API (30 per minute per client IP), so it answers
429 once that budget is spent; those are counted under their own status, not hidden.
`--stage3` sends only the stage-3 read routes (they are not rate limited, so every request counts).
Environment: API_URL (default http://localhost:8000/api/v1).
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import threading
import time
import urllib.parse
from collections import Counter
from itertools import cycle, islice

API = os.environ.get("API_URL", "http://localhost:8000/api/v1").rstrip("/")
MISSING_OCID = "ocds-5wno2w-DOES-NOT-EXIST-1"


def _fetch_json(path: str) -> dict:
    parts = urllib.parse.urlsplit(API + path)
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=60)
    try:
        connection.request("GET", parts.path + ("?" + parts.query if parts.query else ""))
        return json.loads(connection.getresponse().read())
    finally:
        connection.close()


def stage3_routes(ocids: list[str]) -> list[tuple[str, str]]:
    """The stage-3 read routes: aggregates, random process, buyer search, context, region filter."""
    return [
        ("by_region", "/stats/by-region"),
        ("by_year", "/stats/by-year"),
        ("random", "/processes/random"),
        ("random_signals", "/processes/random?with_signals=true"),
        ("random_min_score", "/processes/random?min_score=40"),
        ("buyer_search", "/buyers/search?q=municip"),
        ("buyer_search", "/buyers/search?q=hospital&limit=5"),
        ("buyer_search", "/buyers/search?q=gad%20parroquial"),
        ("context", f"/processes/{ocids[0]}/context"),
        ("context", f"/processes/{ocids[2]}/context"),
        ("list_region", "/processes?region=MANABI&page_size=25"),
        ("glossary", "/glossary"),
    ]


def quotes_routes(ocids: list[str]) -> list[tuple[str, str]]:
    """Quotes, provenance and the awarded-amount filter (stage 4)."""
    routes = [("quotes", f"/processes/{ocid}/quotes") for ocid in ocids[:5]]
    routes += [("provenance", f"/processes/{ocid}/provenance") for ocid in ocids[:5]]
    routes += [
        ("amount_min", "/processes?min_amount=1000000&page_size=25"),
        ("amount_band", "/processes?min_amount=10000&max_amount=500000&sort=-award_total&page_size=25"),
        ("amount_signal", "/processes?min_amount=100000&signal=SINGLE_BIDDER&page_size=10"),
        ("quotes_404", f"/processes/{MISSING_OCID}/quotes"),
        ("amount_422", "/processes?min_amount=-1"),
    ]
    return routes


def build_route_mix(only_stage3: bool = False, only_quotes: bool = False) -> list[tuple[str, str]]:
    """``(label, path)`` pairs; ocids come from the API itself so the mix works on any dataset."""
    items = _fetch_json("/processes?page_size=10&sort=-risk_score")["items"]
    ocids = [item["ocid"] for item in items]
    if only_stage3:
        return stage3_routes(ocids)
    if only_quotes:
        return quotes_routes(ocids)
    mix: list[tuple[str, str]] = [
        ("stats", "/stats"),
        ("list_default", "/processes?page_size=25"),
        ("list_filtered", "/processes?year=2023&min_score=40&page_size=10"),
        ("list_sorted", "/processes?sort=-award_total&page=2&page_size=25"),
        ("list_search", "/processes?q=hospital&page_size=10"),
        ("list_signal", "/processes?signal=SINGLE_BIDDER&sort=-risk_score&page_size=25"),
        ("not_found", f"/processes/{MISSING_OCID}"),
        ("invalid_422", "/processes?page=0"),
    ]
    for ocid in ocids[:5]:
        mix.append(("detail", f"/processes/{ocid}"))
    mix.append(("similar", f"/processes/{ocids[0]}/similar?k=5"))
    mix.append(("dossier", f"/processes/{ocids[1]}/dossier"))
    return mix


def percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, round(fraction * (len(sorted_values) - 1))))
    return sorted_values[index]


def summarise(samples: list[tuple[float, int]]) -> dict:
    latencies = sorted(seconds for seconds, _ in samples)
    return {
        "count": len(samples),
        "p50_s": round(percentile(latencies, 0.50), 4),
        "p95_s": round(percentile(latencies, 0.95), 4),
        "p99_s": round(percentile(latencies, 0.99), 4),
        "max_s": round(latencies[-1], 4) if latencies else 0.0,
        "statuses": dict(sorted(Counter(status for _, status in samples).items())),
    }


def worker(jobs: list[tuple[str, str]], results: list[tuple[str, float, int]], lock: threading.Lock) -> None:
    parts = urllib.parse.urlsplit(API)
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=60)
    local: list[tuple[str, float, int]] = []
    for label, path in jobs:
        started = time.perf_counter()
        try:
            connection.request("GET", API[len(f"{parts.scheme}://{parts.netloc}") :] + path)
            response = connection.getresponse()
            response.read()
            status = response.status
        except (OSError, http.client.HTTPException):
            status = 0  # transport failure
            connection.close()
            connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=60)
        local.append((label, time.perf_counter() - started, status))
    connection.close()
    with lock:
        results.extend(local)


def run(total: int, concurrency: int, only_stage3: bool = False, only_quotes: bool = False) -> dict:
    mix = build_route_mix(only_stage3, only_quotes)
    plan = list(islice(cycle(mix), total))
    shards = [plan[index::concurrency] for index in range(concurrency)]
    results: list[tuple[str, float, int]] = []
    lock = threading.Lock()
    threads = [threading.Thread(target=worker, args=(shard, results, lock)) for shard in shards if shard]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - started
    by_route: dict[str, list[tuple[float, int]]] = {}
    for label, seconds, status in results:
        by_route.setdefault(label, []).append((seconds, status))
    overall = summarise([(seconds, status) for _, seconds, status in results])
    return {
        "api": API,
        "requests": total,
        "concurrency": concurrency,
        "elapsed_s": round(elapsed, 3),
        "requests_per_second": round(len(results) / elapsed, 2) if elapsed else 0.0,
        "overall": overall,
        "routes": {label: summarise(samples) for label, samples in sorted(by_route.items())},
    }


def print_table(report: dict) -> None:
    print(
        f"{report['requests']} requests @ concurrency {report['concurrency']} against {report['api']}: "
        f"{report['elapsed_s']} s, {report['requests_per_second']} req/s"
    )
    print(f"{'route':<15}{'n':>6}{'p50':>9}{'p95':>9}{'p99':>9}{'max':>9}  statuses")
    rows = [*report["routes"].items(), ("OVERALL", report["overall"])]
    for label, row in rows:
        print(
            f"{label:<15}{row['count']:>6}{row['p50_s']:>9.3f}{row['p95_s']:>9.3f}"
            f"{row['p99_s']:>9.3f}{row['max_s']:>9.3f}  {row['statuses']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--requests", type=int, default=200, help="Total requests (default 200).")
    parser.add_argument("--concurrency", type=int, default=8, help="Parallel clients (default 8).")
    parser.add_argument(
        "--stage3",
        action="store_true",
        help="Send only the stage-3 routes (aggregates, random, search, context).",
    )
    parser.add_argument(
        "--quotes",
        action="store_true",
        help="Send only the quotes, provenance and amount-filter routes.",
    )
    parser.add_argument("--json-only", action="store_true", help="Print only the JSON report.")
    args = parser.parse_args()
    report = run(max(1, args.requests), max(1, args.concurrency), args.stage3, args.quotes)
    if not args.json_only:
        print_table(report)
    print(json.dumps(report, indent=None if args.json_only else 2))


if __name__ == "__main__":
    main()
