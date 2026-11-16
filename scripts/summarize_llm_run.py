"""Summarise one controlled LLM dossier run from the investigator trace log.

Usage: python scripts/summarize_llm_run.py <first_line> <last_line> <label> <out.json>
Lines are 1-based and inclusive, referring to data/traces/investigator.jsonl.
Process identifiers are not written to the output.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

TRACE_LOG = Path("data/traces/investigator.jsonl")


def summarise(first: int, last: int, label: str) -> dict:
    runs = [json.loads(line) for line in TRACE_LOG.read_text(encoding="utf-8").splitlines()[first - 1 : last]]
    passed_first = sum(1 for r in runs if r["final_mode"] == "llm" and r["llm_attempts"] == 1)
    passed_retry = sum(1 for r in runs if r["final_mode"] == "llm" and r["llm_attempts"] > 1)
    fallback = sum(1 for r in runs if r["final_mode"] == "template")
    rejected = Counter(
        token for r in runs for attempt in r["attempt_log"] for token in attempt.get("rejected") or []
    )
    latencies = sorted(r["total_ms"] for r in runs)
    return {
        "label": label,
        "runs": len(runs),
        "model": sorted({r["model"] for r in runs if r.get("model")}),
        "started_at_first": runs[0]["started_at"],
        "started_at_last": runs[-1]["started_at"],
        "llm_passed_first_attempt": passed_first,
        "llm_passed_after_retry": passed_retry,
        "fell_back_to_template": fallback,
        "final_dossiers_passing_grounding": sum(1 for r in runs if r["grounding_passed"]),
        "llm_calls": sum(r["llm_attempts"] for r in runs),
        "prompt_tokens": sum(r["prompt_tokens"] or 0 for r in runs),
        "completion_tokens": sum(r["completion_tokens"] or 0 for r in runs),
        "latency_ms_median": latencies[len(latencies) // 2],
        "latency_ms_max": latencies[-1],
        "rejected_tokens_top": rejected.most_common(15),
    }


if __name__ == "__main__":
    first, last, label, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
    existing = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {"runs": []}
    existing["runs"].append(summarise(first, last, label))
    out.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(existing["runs"][-1], ensure_ascii=False, indent=2))
