#!/usr/bin/env python3
"""End-to-end smoke test for the running local stack (standard library only).

    python3 scripts/smoke_test.py            # API on :8000, web on :3000, db service via docker compose

Environment: API_URL, WEB_URL, EXPECTED_PROCESSES (default 2251027). Exit code 1 if any check fails.
The test writes nothing: reviews are disabled by default and the refused write is itself a check.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("API_URL", "http://localhost:8000/api/v1").rstrip("/")
WEB = os.environ.get("WEB_URL", "http://localhost:3000").rstrip("/")
EXPECTED = int(os.environ.get("EXPECTED_PROCESSES", "2251027"))

results: list[tuple[bool, str]] = []


def request(url: str, body: dict | None = None, timeout: int = 120) -> tuple[int, bytes]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((ok, name))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    return ok


def get_json(path: str) -> tuple[int, dict]:
    status, raw = request(f"{API}{path}")
    return status, json.loads(raw) if raw else {}


def main() -> int:
    status, health = get_json("/health")
    check(
        "api /health",
        status == 200 and health.get("status") == "ok",
        f"tables_present={sum(health.get('tables', {}).values())}/{len(health.get('tables', {}))}",
    )

    status, stats = get_json("/stats")
    total = stats.get("processes_total")
    check(f"api /stats returns {EXPECTED:,} processes", status == 200 and total == EXPECTED, f"got {total}")

    status, page = get_json("/processes?page_size=5&sort=-risk_score")
    items = page.get("items", [])
    check(
        "api process list page",
        status == 200 and len(items) == 5 and page.get("total") == EXPECTED,
        f"total={page.get('total')}",
    )
    if not items:
        return finish()
    ocid, supplier = items[0]["ocid"], items[0].get("winner_ruc")

    status, detail = get_json(f"/processes/{ocid}")
    check("api process detail", status == 200 and detail.get("ocid", ocid) == ocid, ocid)

    status, dossier = get_json(f"/processes/{ocid}/dossier")
    check("api dossier", status == 200 and bool(dossier.get("summary_es")), f"mode={dossier.get('mode')}")

    if supplier:
        status, profile = get_json(f"/suppliers/{supplier}")
        check(
            "api company supplier page",
            status == 200,
            f"{supplier} kind={profile.get('profile', {}).get('kind')}",
        )
    else:
        check("api company supplier page", False, "top process has no winner_ruc")

    # Reviews are disabled by default: an anonymous write must be refused and store nothing.
    status_meta, meta = get_json("/meta")
    status_post, _ = request(
        f"{API}/processes/{ocid}/reviews", {"status": "pending", "note": "smoke test", "reviewer": "smoke"}
    )
    status_get, listed = get_json(f"/processes/{ocid}/reviews")
    rows = listed.get("items", listed) if isinstance(listed, dict) else listed
    check(
        "api anonymous review write is refused",
        status_meta == 200 and meta.get("reviews_enabled") is False and status_post in (401, 403),
        f"reviews_enabled={meta.get('reviews_enabled')} POST http {status_post}",
    )
    check(
        "api no review stored by the refused write",
        status_get == 200 and not any(row.get("reviewer") == "smoke" for row in rows),
        f"rows={len(rows)}",
    )

    for path in ("/", "/procesos", "/metodologia", f"/procesos/{ocid}"):
        code, body = request(f"{WEB}{path}")
        check(f"web {path[:48]}", code == 200 and b"Veedor" in body, f"http {code}, {len(body)} bytes")
    return finish()


def finish() -> int:
    failed = [name for ok, name in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
