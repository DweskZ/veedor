#!/usr/bin/env python3
"""Regenerates grafana/dashboards/veedor.json (the dashboard is committed; this is its source).

python3 ops/observability/build_dashboard.py
"""

# ruff: noqa: E501
import json
from pathlib import Path

PROM = {"type": "prometheus", "uid": "prometheus"}
TEMPO = {"type": "tempo", "uid": "tempo"}
RATE = "$__rate_interval"
HTTP = "http_server_request_duration_seconds"
TOOL = "veedor_tool_duration_milliseconds"
_id = 0


def _panel(kind, title, description, x, y, w, h, targets, datasource=PROM, unit=None, extra=None):
    global _id
    _id += 1
    panel = {
        "id": _id,
        "type": kind,
        "title": title,
        "description": description,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": datasource,
        "targets": [
            {"refId": chr(65 + i), "datasource": datasource, **target} for i, target in enumerate(targets)
        ],
        "fieldConfig": {"defaults": {"unit": unit} if unit else {}, "overrides": []},
        "options": {},
    }
    if extra:
        for key, value in extra.items():
            if key == "fieldConfig":
                panel[key]["defaults"].update(value["defaults"])
            else:
                panel[key].update(value)
    return panel


def expr(query, legend):
    return {"expr": query, "legendFormat": legend}


def quantile(q, metric, by):
    return f"histogram_quantile({q}, sum by (le, {by}) (rate({metric}_bucket[{RATE}])))"


def row(title, y):
    global _id
    _id += 1
    return {
        "id": _id,
        "type": "row",
        "title": title,
        "collapsed": False,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
    }


panels = [
    row("API (RED)", 0),
    _panel(
        "timeseries",
        "Request rate by route",
        "How much traffic does each route receive? (requests per second, route template)",
        0,
        1,
        8,
        8,
        [expr(f"sum by (http_route) (rate({HTTP}_count[{RATE}]))", "{{http_route}}")],
        unit="reqps",
    ),
    _panel(
        "timeseries",
        "Errors by route and status class",
        "Which routes fail? Server errors (5xx) and client errors (4xx) per second.",
        8,
        1,
        8,
        8,
        [
            expr(
                f'sum by (http_route) (rate({HTTP}_count{{http_response_status_code=~"5.."}}[{RATE}]))',
                "5xx {{http_route}}",
            ),
            expr(
                f'sum by (http_route) (rate({HTTP}_count{{http_response_status_code=~"4.."}}[{RATE}]))',
                "4xx {{http_route}}",
            ),
        ],
        unit="reqps",
    ),
    _panel(
        "timeseries",
        "Latency p50 / p95 by route",
        "How slow are requests? Median and 95th percentile per route template.",
        16,
        1,
        8,
        8,
        [
            expr(quantile(0.5, HTTP, "http_route"), "p50 {{http_route}}"),
            expr(quantile(0.95, HTTP, "http_route"), "p95 {{http_route}}"),
        ],
        unit="s",
    ),
    row("Investigations", 9),
    _panel(
        "bargauge",
        "Investigations by final mode",
        "How many investigations finished, and in which mode (template or llm)? (cumulative counter, latest value in the selected range)",
        0,
        10,
        6,
        8,
        [
            expr(
                "sum by (final_mode) (last_over_time(veedor_investigations_total[$__range]))",
                "{{final_mode}}",
            )
        ],
    ),
    _panel(
        "bargauge",
        "Specialist runs",
        "Which specialist agents ran, and how often? (cumulative counter, latest value in the selected range)",
        6,
        10,
        6,
        8,
        [
            expr(
                "sum by (specialist) (last_over_time(veedor_specialist_runs_total[$__range]))",
                "{{specialist}}",
            )
        ],
    ),
    _panel(
        "barchart",
        "Tool-call outcomes by tool",
        "Which tools succeed (ok) and which time out or hit upstream errors? (cumulative counter, latest value in the selected range)",
        12,
        10,
        12,
        8,
        [
            {
                **expr(
                    "sum by (tool, outcome) (last_over_time(veedor_tool_calls_total[$__range]))",
                    "{{tool}} / {{outcome}}",
                ),
                "instant": True,
                "format": "table",
            }
        ],
        extra={"options": {"xField": "tool", "stacking": "normal"}},
    ),
    row("Tools, tokens and grounding", 18),
    _panel(
        "timeseries",
        "Tool latency p50 / p95 by tool",
        "How long do external lookups take? Median and 95th percentile per tool.",
        0,
        19,
        10,
        8,
        [
            expr(quantile(0.5, TOOL, "tool"), "p50 {{tool}}"),
            expr(quantile(0.95, TOOL, "tool"), "p95 {{tool}}"),
        ],
        unit="ms",
    ),
    _panel(
        "stat",
        "Tokens per investigation",
        "How many model tokens does one investigation cost on average? (cumulative counters; empty when no model is used)",
        10,
        19,
        7,
        8,
        [
            expr(
                "sum(last_over_time(veedor_llm_tokens_total[$__range])) / sum(last_over_time(veedor_investigations_total[$__range]))",
                "tokens",
            )
        ],
        extra={
            "fieldConfig": {
                "defaults": {"noValue": "no LLM usage", "color": {"mode": "fixed", "fixedColor": "blue"}}
            }
        },
    ),
    _panel(
        "gauge",
        "Grounding pass rate",
        "What share of generated text passed the grounding verifier? (cumulative counter, latest value in the selected range)",
        17,
        19,
        7,
        8,
        [
            expr(
                'sum(last_over_time(veedor_grounding_results_total{passed="true"}[$__range])) / sum(last_over_time(veedor_grounding_results_total[$__range]))',
                "pass rate",
            )
        ],
        unit="percentunit",
        extra={"fieldConfig": {"defaults": {"min": 0, "max": 1, "noValue": "no data"}}},
    ),
    row("Traces", 27),
    _panel(
        "table",
        "Recent traces (Tempo)",
        "Latest request and investigation traces; open one to see its spans.",
        0,
        28,
        24,
        9,
        [
            {
                "queryType": "traceql",
                "query": '{ resource.service.name =~ "veedor.*" }',
                "limit": 20,
                "tableType": "traces",
            }
        ],
        datasource=TEMPO,
    ),
]

dashboard = {
    "uid": "veedor",
    "title": "Veedor",
    "tags": ["veedor"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "10s",
    "time": {"from": "now-30m", "to": "now"},
    "panels": panels,
}
out = Path(__file__).parent / "grafana" / "dashboards" / "veedor.json"
out.write_text(json.dumps(dashboard, indent=2) + "\n")
print(f"wrote {out} ({len(panels)} panels incl. rows)")
