#!/usr/bin/env python3
"""Verify the telemetry pipeline end to end by querying Tempo and Prometheus (standard library only).

    uv run python scripts/generate_traffic.py && uv run python scripts/verify_telemetry.py

Environment: TEMPO_URL (default http://localhost:3200), PROMETHEUS_URL (default http://localhost:9090),
WAIT_SECONDS (default 45: data takes a few seconds to arrive), SINCE_SECONDS (default 300:
trace window). Exit code 1 if any check fails.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

TEMPO = os.environ.get("TEMPO_URL", "http://localhost:3200").rstrip("/")
PROM = os.environ.get("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
WAIT_SECONDS = int(os.environ.get("WAIT_SECONDS", "45"))
SINCE_SECONDS = int(os.environ.get("SINCE_SECONDS", "300"))  # only look at recent traffic

API_SERVICE = "veedor-api"
THIRTEEN_DIGITS = re.compile(r"\d{13}")
OCDS = re.compile(r"ocds-")
ALLOWED_SPAN_NAME = re.compile(r"^(GET|POST|HEAD|PUT|PATCH|DELETE|OPTIONS|_OTHER) (/api/v1/\S*|unmatched)$")
EXPECTED_SERIES = {  # metric -> why it must exist after generate_traffic.py
    "http_server_request_duration_seconds_count": "API request metrics",
    "veedor_investigations_total": "investigations by final mode",
    "veedor_specialist_runs_total": "specialist runs",
    "veedor_tool_calls_total": "tool calls by outcome",
    "veedor_tool_duration_milliseconds_count": "tool latency",
    "veedor_grounding_results_total": "grounding results",
}

results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((ok, name))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    return ok


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read())


def attribute_value(raw: dict) -> str:
    return str(next(iter(raw.values()), ""))


def fetch_spans(service_filter: str = "veedor.*") -> list[dict]:
    """Every span of recent traces of our services, with flattened attributes."""
    now = int(time.time())
    query = urllib.parse.urlencode(
        {
            "q": f'{{ resource.service.name =~ "{service_filter}" }}',
            "limit": 200,
            "start": now - SINCE_SECONDS,
            "end": now + 60,
        }
    )
    traces = get_json(f"{TEMPO}/api/search?{query}").get("traces", [])
    spans: list[dict] = []
    for trace in traces:
        body = get_json(f"{TEMPO}/api/traces/{trace['traceID']}")
        for batch in body.get("batches", []) + body.get("resourceSpans", []):
            resource = {
                a["key"]: attribute_value(a["value"]) for a in batch.get("resource", {}).get("attributes", [])
            }
            for scope in batch.get("scopeSpans", []) + batch.get("instrumentationLibrarySpans", []):
                for raw in scope.get("spans", []):
                    if int(raw.get("startTimeUnixNano", 0)) < (now - SINCE_SECONDS) * 10**9:
                        continue  # Tempo's time filter works on blocks: drop older spans here
                    attributes = {a["key"]: attribute_value(a["value"]) for a in raw.get("attributes", [])}
                    spans.append({"name": raw["name"], "attributes": attributes, "resource": resource})
    return spans


def prom_query(expression: str) -> list[dict]:
    url = f"{PROM}/api/v1/query?{urllib.parse.urlencode({'query': expression})}"
    return get_json(url)["data"]["result"]


def prom_total(metric: str) -> float:
    return sum(float(item["value"][1]) for item in prom_query(f"sum({metric})"))


def data_is_complete() -> bool:
    """Prometheus has the counters and Tempo already shows a 422 request and an investigation."""
    if (
        prom_total("http_server_request_duration_seconds_count") <= 0
        or prom_total("veedor_tool_calls_total") <= 0
    ):
        return False
    spans = fetch_spans()
    has_422 = any(s["attributes"].get("http.response.status_code") == "422" for s in spans)
    return has_422 and any(s["name"] == "investigation" for s in spans)


def wait_for_data() -> None:
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        try:
            if data_is_complete():
                return
        except OSError:
            pass
        time.sleep(3)


def leaked_identifiers(spans: list[dict]) -> list[str]:
    bad = []
    for item in spans:
        texts = [("span name", item["name"])]
        texts += [(f"attribute {k}", v) for k, v in item["attributes"].items() if k != "ocid"]
        texts += [(f"resource {k}", v) for k, v in item["resource"].items()]
        for where, text in texts:
            if THIRTEEN_DIGITS.search(text) or OCDS.search(text):
                bad.append(f"{where}: {text[:60]}")
    return bad


def verify_traces() -> None:
    spans = fetch_spans()
    api = [
        s
        for s in spans
        if s["resource"].get("service.name") == API_SERVICE and "http.route" in s["attributes"]
    ]
    check("traces: API request spans exist", len(api) > 0, f"{len(api)} request spans of {len(spans)} spans")
    names = sorted({s["name"] for s in api})
    check(
        "traces: request span names are route templates",
        bool(api) and all(ALLOWED_SPAN_NAME.match(n) for n in names) and any("{ocid}" in n for n in names),
        f"{len(names)} distinct names, e.g. {names[:3]}",
    )
    check(
        "traces: no raw path as route attribute",
        all(
            s["attributes"]["http.route"] == "unmatched" or s["attributes"]["http.route"] in s["name"]
            for s in api
        ),
    )
    check("traces: /health is not traced", not any(n.endswith("/health") for n in names))
    codes = sorted({s["attributes"].get("http.response.status_code", "?") for s in api})
    check(
        "traces: success, 404 and 422 requests were recorded",
        {"200", "404", "422"} <= set(codes),
        f"status codes {codes}",
    )
    leaks = leaked_identifiers(spans)
    check(
        "traces: no 13-digit number or ocds- id outside the ocid attribute",
        not leaks,
        f"{len(spans)} spans scanned {leaks[:3]}",
    )
    investigation = [
        s
        for s in spans
        if s["name"] in ("investigation", "specialist", "tool.call") or s["name"].startswith("node ")
    ]
    check(
        "traces: investigation/specialist/tool spans exist",
        len(investigation) > 0,
        f"{len(investigation)} spans",
    )
    ocid_spans = [s for s in spans if "ocid" in s["attributes"]]
    check("traces: ocid attribute present on some spans", len(ocid_spans) > 0, f"{len(ocid_spans)} spans")


def verify_metrics() -> None:
    for metric, why in EXPECTED_SERIES.items():
        total = prom_total(metric)
        check(f"metrics: {metric} non-zero", total > 0, f"{why}; total {total:g}")
    tokens = prom_total("veedor_llm_tokens_total")  # only non-zero when an LLM-backed run happened
    print(f"[INFO] metrics: veedor_llm_tokens_total total {tokens:g} (zero is expected for --no-llm runs)")
    labels_seen = 0
    leaks = []
    for metric in ("http_server_request_duration_seconds_count", "veedor_tool_calls_total"):
        for item in prom_query(metric):
            for key, value in item["metric"].items():
                labels_seen += 1
                if THIRTEEN_DIGITS.search(value) or OCDS.search(value):
                    leaks.append(f"{key}={value[:40]}")
    check("metrics: no identifier in any label value", not leaks, f"{labels_seen} labels scanned {leaks[:3]}")
    routes = {
        item["metric"].get("http_route", "")
        for item in prom_query("http_server_request_duration_seconds_count")
    }
    check(
        "metrics: http_route labels are templates",
        any("{ocid}" in r for r in routes),
        f"{len(routes)} routes",
    )


def main() -> int:
    print(f"waiting up to {WAIT_SECONDS}s for data in Tempo ({TEMPO}) and Prometheus ({PROM}) ...")
    wait_for_data()
    try:
        verify_traces()
        verify_metrics()
    except OSError as error:
        check("stores reachable", False, str(error))
    failed = [name for ok, name in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
