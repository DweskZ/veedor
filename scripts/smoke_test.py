#!/usr/bin/env python3
"""End-to-end smoke test for the running local stack (standard library only).

    python3 scripts/smoke_test.py            # API on :8000, web on :3000, db service via docker compose

Environment: API_URL, WEB_URL, EXPECTED_PROCESSES (default 2251027). Exit code 1 if any check fails.
The test writes nothing: reviews are disabled by default and the refused write is itself a check.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = os.environ.get("API_URL", "http://localhost:8000/api/v1").rstrip("/")
WEB = os.environ.get("WEB_URL", "http://localhost:3000").rstrip("/")
EXPECTED = int(os.environ.get("EXPECTED_PROCESSES", "2251027"))

# The API accepts only identifiers with this shape (see src/veedor/api/params.py).
_OCID_FIRST = r"A-Za-z0-9ÑÇÓ._\-,:+()&º°·–—‐‒−－"
API_OCID = re.compile(rf"ocds-5wno2w-[{_OCID_FIRST}][{_OCID_FIRST} ]{{0,119}}")

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

    status, similar = get_json(f"/processes/{ocid}/similar?k=3")
    neighbours = similar.get("items", []) if isinstance(similar, dict) else similar
    check(
        "api similar processes",
        status == 200 and 1 <= len(neighbours) <= 3 and all(n.get("ocid") != ocid for n in neighbours),
        f"http {status}, {len(neighbours)} neighbours",
    )

    stored_ocid = first_stored_investigation()
    if stored_ocid is None:
        check("api stored investigation", False, "no stored investigation found under data/investigations")
    else:
        encoded = urllib.parse.quote(stored_ocid, safe="")
        status, investigation = get_json(f"/processes/{encoded}/investigation")
        specialists = investigation.get("specialists") or []
        check(
            "api stored investigation",
            status == 200 and investigation.get("ocid") == stored_ocid and bool(specialists),
            f"http {status}, specialists={len(specialists)}",
        )
    status, _ = get_json("/processes/ocds-5wno2w-NO-EXISTE-0001/investigation")
    check("api investigation is never started on demand", status == 404, f"http {status}")

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

    check_stage3_endpoints(ocid)
    check_quotes_and_provenance(ocid)
    check_ask(ocid)

    for path in ("/", "/procesos", "/metodologia", f"/procesos/{ocid}"):
        code, body = request(f"{WEB}{path}")
        check(f"web {path[:48]}", code == 200 and b"Veedor" in body, f"http {code}, {len(body)} bytes")
    return finish()


def check_stage3_endpoints(ocid: str) -> None:
    """The stage-3 read endpoints: aggregates, random process, buyer search, context, glossary."""
    status, regions = get_json("/stats/by-region")
    items = regions.get("items", [])
    national = regions.get("national", {})
    provinces = [row for row in items if row.get("region") != "SIN_REGION"]
    check(
        "api /stats/by-region",
        status == 200
        and len(provinces) == 24
        and regions.get("basis") == "competitive"
        and national.get("competitive_processes") == sum(row["competitive_processes"] for row in items)
        and all(row.get("region_label") for row in items),
        f"{len(provinces)} provinces, national {national.get('pct_with_signal')} %",
    )
    status, years = get_json("/stats/by-year")
    rows = years.get("items", [])
    check(
        "api /stats/by-year",
        status == 200
        and len(rows) >= 2
        and rows[-1].get("partial_year") is True
        and bool(years.get("notes")),
        f"{rows[0].get('year')}-{rows[-1].get('year')}" if rows else "no rows",
    )
    if provinces:
        key = urllib.parse.quote(provinces[0]["region"])
        status, listed = get_json(f"/processes?region={key}&page_size=1")
        check(
            "api /processes?region= matches the province row",
            status == 200 and listed.get("total") == provinces[0]["processes_total"],
            f"{provinces[0]['region']} total={listed.get('total')}",
        )
    status, _ = get_json("/processes?region=ATLANTIDA")
    check("api unknown region is rejected", status == 422, f"http {status}")

    status, picked = get_json("/processes/random?with_signals=true")
    check(
        "api /processes/random with signals",
        status == 200
        and API_OCID.fullmatch(picked.get("ocid", "")) is not None
        and picked.get("n_signals", 0) > 0,
        picked.get("ocid", ""),
    )
    status, buyers = get_json("/buyers/search?q=municip")
    hits = buyers.get("items", [])
    check(
        "api /buyers/search",
        status == 200 and 0 < len(hits) <= 10 and all(len(hit.get("ruc", "")) == 13 for hit in hits),
        f"{len(hits)} hits",
    )
    status, _ = get_json("/buyers/search?q=ab")
    check("api buyer search needs 3 characters", status == 422, f"http {status}")

    status, context = get_json(f"/processes/{ocid}/context")
    check(
        "api /processes/{ocid}/context",
        status == 200 and context.get("ocid") == ocid and context.get("comparable_processes", 0) >= 1,
        f"{context.get('method')} {context.get('year')}, {context.get('comparable_processes')} comparable",
    )
    status, glossary = get_json("/glossary")
    terms = glossary.get("items", [])
    check(
        "api /glossary",
        status == 200 and len(terms) > 0 and all(t.get("term") and t.get("definition_es") for t in terms),
        f"{len(terms)} terms",
    )


def check_ask(ocid: str) -> None:
    """Question answering: off by default (404); when switched on, answers from stored evidence only."""
    status_meta, meta = get_json("/meta")
    enabled = meta.get("ask_enabled") is True
    body = {"question": "¿Cuántos oferentes hubo en este proceso?"}
    status, raw = request(f"{API}/processes/{ocid}/ask", body)
    answer = json.loads(raw) if raw else {}
    if not enabled:
        check("api ask is off by default (404)", status_meta == 200 and status == 404, f"http {status}")
        return
    sentences = answer.get("sentences", [])
    check(
        "api ask answers from stored evidence",
        status == 200
        and answer.get("mode") in ("model", "retrieval")
        and answer.get("ocid") == ocid
        and bool(sentences)
        and all(all(s.get(k) for k in ("fact_id", "source_id", "source_field", "text")) for s in sentences),
        f"mode={answer.get('mode')}, {len(sentences)} sentences",
    )
    status, raw = request(f"{API}/processes/{ocid}/ask", {"question": "¿Hubo corrupción en este proceso?"})
    judged = json.loads(raw) if raw else {}
    check(
        "api ask refuses to judge",
        status == 200 and judged.get("answerable") is False and judged.get("sentences") == [],
        f"reason={judged.get('reason')}",
    )
    status, _ = request(f"{API}/processes/{ocid}/ask", {"question": "uno\ndos"})
    check("api ask rejects a malformed question (422)", status == 422, f"http {status}")


def check_quotes_and_provenance(ocid: str) -> None:
    """Quotes from the process's own text, provenance of every fact, and the awarded-amount filter."""
    status_meta, meta = get_json("/meta")
    check(
        "api /meta reports the feature flags",
        status_meta == 200
        and isinstance(meta.get("ask_enabled"), bool)
        and isinstance(meta.get("quotes_enabled"), bool)
        and isinstance(meta.get("reviews_enabled"), bool),
        f"ask_enabled={meta.get('ask_enabled')} quotes_enabled={meta.get('quotes_enabled')}",
    )
    status, quotes = get_json(f"/processes/{ocid}/quotes")
    if meta.get("quotes_enabled") is not True:
        check("api quotes are off by default (404)", status == 404, f"http {status}")
        status, _ = get_json("/processes/ocds-5wno2w-NO-EXISTE-0001/quotes")
        check("api quotes off: unknown process is also 404", status == 404, f"http {status}")
        check_provenance_and_amounts(ocid)
        return
    items = quotes.get("items", [])
    omitted = quotes.get("omitted", {})
    check(
        "api /processes/{ocid}/quotes",
        status == 200
        and quotes.get("ocid") == ocid
        and len(items) <= 3
        and set(omitted) == {"personal_data", "unsafe", "below_relevance"}
        and "no son palabras de veedor" in quotes.get("note_es", "").lower()
        and all(it.get("text") and it.get("source_field") and it.get("related_signal") for it in items),
        f"{len(items)} quotes, available_total={quotes.get('available_total')}",
    )
    status, _ = get_json("/processes/ocds-5wno2w-NO-EXISTE-0001/quotes")
    check("api quotes: unknown process is 404", status == 404, f"http {status}")
    check_provenance_and_amounts(ocid)


def check_provenance_and_amounts(ocid: str) -> None:
    status, provenance = get_json(f"/processes/{ocid}/provenance")
    facts = provenance.get("facts", [])
    keys = {fact.get("key") for fact in facts}
    source_ids = {source.get("id") for source in provenance.get("sources", [])}
    check(
        "api /processes/{ocid}/provenance",
        status == 200
        and provenance.get("ocid") == ocid
        and {"facts.budget", "facts.n_tenderers", "score.risk_score"} <= keys
        and all(f.get("source_id") in source_ids and f.get("verify_es") for f in facts)
        and any(k.startswith("signal.") for k in keys)
        and all(not f.get("derived") or f.get("derivation_es") for f in facts),
        f"{len(facts)} facts, {len(source_ids)} sources",
    )
    sercop = next((s for s in provenance.get("sources", []) if s.get("id") == "sercop_ocds"), {})
    check(
        "api provenance cites the SERCOP licence",
        sercop.get("licence", "").startswith("CC BY 3.0 EC") and bool(sercop.get("retrieved_at")),
        sercop.get("licence", ""),
    )
    status, _ = get_json("/processes/ocds-5wno2w-NO-EXISTE-0001/provenance")
    check("api provenance: unknown process is 404", status == 404, f"http {status}")

    status, everything = get_json("/processes?page_size=1")
    status_min, over = get_json("/processes?min_amount=1000000&page_size=1")
    status_max, under = get_json("/processes?max_amount=999999.99&page_size=1")
    status_band, band = get_json("/processes?min_amount=1000&max_amount=1000000&page_size=1")
    total = everything.get("total", 0)
    check(
        "api /processes amount filter",
        status == status_min == status_max == status_band == 200
        and 0 < over.get("total", 0) < total
        and over["total"] + under["total"] <= total  # processes without an amount match neither bound
        and band.get("total", 0) <= under["total"]
        and all(row.get("award_total", 0) >= 1_000_000 for row in over.get("items", [])),
        f"min 1e6 -> {over.get('total')}, max <1e6 -> {under.get('total')}, of {total}",
    )
    for bad in ("min_amount=-1", "max_amount=abc", "min_amount=nan", "min_amount=5&max_amount=1"):
        status, _ = get_json(f"/processes?{bad}")
        check(f"api amount filter rejects {bad}", status == 422, f"http {status}")


def first_stored_investigation() -> str | None:
    """Return the ocid of one investigation stored on the host, if any."""
    folder = Path(os.environ.get("INVESTIGATIONS_DIR", "data/investigations"))
    for path in sorted(folder.glob("*.json")):
        try:
            ocid = json.loads(path.read_text(encoding="utf-8")).get("ocid")
        except (OSError, ValueError):
            continue
        if isinstance(ocid, str) and API_OCID.fullmatch(ocid):
            return ocid
    return None


def finish() -> int:
    failed = [name for ok, name in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
