#!/usr/bin/env python3
"""Generate traffic for the observability stack.

    uv run python scripts/generate_traffic.py [--rounds 3]

1. Calls a spread of API routes (list, detail, dossier, similar, investigation, supplier, buyer,
   404s and a 422) against API_URL (default http://localhost:8000/api/v1).
2. Runs `veedor investigate batch --top 3 --no-llm` with telemetry enabled when that CLI exists.
   Otherwise it emits ONE CLEARLY LABELLED SYNTHETIC investigation (service name
   `veedor-synthetic-traffic`, no real tool calls) through the public telemetry helpers, so the
   pipeline can still be verified end to end. The output says which of the two happened.

Environment: API_URL, OTEL_ENDPOINT (default http://localhost:4318).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = os.environ.get("API_URL", "http://localhost:8000/api/v1").rstrip("/")
OTEL_ENDPOINT = os.environ.get("OTEL_ENDPOINT", "http://localhost:4318")
SYNTHETIC_SERVICE = "veedor-synthetic-traffic"
CLI_BATCH = ["uv", "run", "veedor", "investigate", "batch", "--top", "3", "--no-llm"]


def call(path: str) -> int:
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=60) as response:
            response.read()
            return response.status
    except urllib.error.HTTPError as error:
        error.read()
        return error.code


def get_json(path: str) -> dict:
    with urllib.request.urlopen(f"{API}{path}", timeout=60) as response:
        return json.loads(response.read())


def drive_api(rounds: int) -> dict[int, int]:
    top = get_json("/processes?page_size=5&sort=-risk_score")["items"]
    ocid, winner, buyer = top[0]["ocid"], top[0].get("winner_ruc"), top[0].get("buyer_ruc")
    paths = [
        "/stats",
        "/meta",
        "/signals",
        "/processes?page_size=25&sort=-risk_score",
        "/processes?year=2023&min_score=40&page_size=10",
        "/processes?q=hospital&page_size=10",
        f"/processes/{ocid}",
        f"/processes/{ocid}/dossier",
        f"/processes/{ocid}/similar?k=5",  # 404/503 until the vectors router exists
        f"/processes/{ocid}/investigation",  # 404 until a stored investigation exists
        "/processes/ocds-5wno2w-DOES-NOT-EXIST-1",  # 404
        "/suppliers/9999999999999",  # 404
        "/processes?page=0",  # 422
        "/suppliers/not-a-ruc",  # 422
    ]
    if winner:
        paths.append(f"/suppliers/{winner}")
    if buyer:
        paths.append(f"/buyers/{buyer}")
    statuses: dict[int, int] = {}
    for _ in range(rounds):
        for path in paths:
            code = call(path)
            statuses[code] = statuses.get(code, 0) + 1
    print(
        f"API: {rounds * len(paths)} requests over {len(paths)} routes; "
        f"status counts {dict(sorted(statuses.items()))}"
    )
    return statuses


def cli_available() -> bool:
    done = subprocess.run(["uv", "run", "veedor", "investigate", "--help"], capture_output=True, check=False)
    return done.returncode == 0


def run_cli_batch() -> bool:
    env = {**os.environ, "VEEDOR_OTEL_ENDPOINT": OTEL_ENDPOINT, "VEEDOR_OTEL_SERVICE_NAME": "veedor-cli"}
    done = subprocess.run(CLI_BATCH, env=env, capture_output=True, text=True, check=False)
    print(f"CLI: `{' '.join(CLI_BATCH[2:])}` exit code {done.returncode}")
    if done.returncode != 0:
        print(done.stderr[-500:])
    return done.returncode == 0


def emit_synthetic_investigation(ocid: str) -> None:
    """A fake investigation through the public helpers. Not real data: labelled by service name."""
    os.environ["VEEDOR_OTEL_ENDPOINT"] = OTEL_ENDPOINT
    from veedor.core.settings import get_settings
    from veedor.infrastructure.telemetry import (
        record_grounding,
        record_investigation,
        record_llm_usage,
        record_specialist_run,
        record_tool_call,
        setup_telemetry,
        shutdown_telemetry,
        span,
    )

    get_settings.cache_clear()
    setup_telemetry(SYNTHETIC_SERVICE)
    plan = [
        ("company_agent", [("get_compania_info", "ok", 850.0), ("get_financials", "upstream_error", 1900.0)]),
        ("tax_registry_agent", [("get_sri_ruc_info", "upstream_error", 640.0)]),
        ("audit_agent", [("get_contraloria_informe", "timeout", 5000.0)]),
    ]
    with span("investigation", ocid=ocid, mode="synthetic"):
        for specialist, calls in plan:
            with span("specialist", specialist=specialist, n_tool_calls=len(calls)):
                for tool, outcome, duration in calls:
                    with span("tool.call", tool=tool, outcome=outcome, duration_ms=duration):
                        record_tool_call(tool, outcome, duration)
            record_specialist_run(specialist)
        record_llm_usage("synthetic-model", 1200, 300)
        record_grounding(True, "template")
        record_investigation("template", 7400.0)
    shutdown_telemetry()
    print(
        f"SYNTHETIC investigation emitted as service '{SYNTHETIC_SERVICE}' for {ocid} (not real tool calls)"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    try:
        drive_api(args.rounds)
        ocid = get_json("/processes?page_size=1&sort=-risk_score")["items"][0]["ocid"]
    except (urllib.error.URLError, KeyError, IndexError) as error:
        print(f"API not reachable or empty: {error}")
        return 1
    if cli_available():
        return 0 if run_cli_batch() else 1
    print("CLI `veedor investigate` not available yet: falling back to a synthetic investigation")
    emit_synthetic_investigation(ocid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
