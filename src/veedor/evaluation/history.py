"""Analysis history: one entry per back-test run, kept in eval/history.json.

The history makes rule changes visible next to the metric they were evaluated on, which matters
because rules tuned after looking at a metric on the same labels make that metric optimistic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson


def load(path: Path) -> list[dict[str, Any]]:
    return orjson.loads(path.read_bytes()) if path.exists() else []


def entry_from(result: dict[str, Any], note: str) -> dict[str, Any]:
    key = result["meta"]["headline"]
    scores = result["primary"]["scores"]
    return {
        "generated_at": result["meta"]["generated_at"],
        "note": note,
        "headline_key": key,
        "headline_auc": scores[key]["auc"],
        "n_positives": result["primary"]["n_positives"],
        "n_unlabelled": result["primary"]["n_unlabelled"],
        "n_boot": result["meta"]["n_boot"],
        "seed": result["meta"]["seed"],
    }


def append(path: Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Append an entry (replacing one with the same timestamp) and persist the list."""
    entries = [e for e in load(path) if e["generated_at"] != entry["generated_at"]]
    entries.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(entries, option=orjson.OPT_INDENT_2))
    return entries
