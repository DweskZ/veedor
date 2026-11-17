# ruff: noqa: E501
"""The generated section of docs/EVALUATION.md (numbers only, no question or answer text)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

DOC_BEGIN = "<!-- BEGIN GENERATED: qa -->"
DOC_END = "<!-- END GENERATED: qa -->"


def _ci(block: dict[str, Any], pct: bool = True) -> str:
    mean, ci = block.get("mean"), block.get("ci95")
    if mean is None or ci is None:
        return "n/a"
    f = (lambda v: f"{100 * v:.1f} %") if pct else (lambda v: f"{v:.3f}")
    return f"{f(mean)} [{f(ci[0])}, {f(ci[1])}]"


def _mode_rows(summary: dict[str, Any]) -> list[tuple[str, str]]:
    a, u, adv, g, lat = (summary[k] for k in ("answerable", "unanswerable", "adversarial", "grounding", "latency_ms"))
    return [
        ("Questions", f"{summary['questions']:,}"),
        ("Recall of selected facts (answerable)", _ci(a["recall"])),
        ("Precision of selected facts (answerable)", _ci(a["precision"])),
        ("At least one expected fact selected (answerable)", _ci(a["hit_rate"])),
        ("Answerable questions answered with no fact", _ci(a["abstained_wrongly"])),
        ("Abstention on unanswerable questions", _ci(u["abstention_rate"])),
        ("Attack questions / distinct attacks", f"{adv['questions']} / {adv['distinct_attacks']}"),
        ("**Attack successes**", f"**{adv['attack_success_count']}**"),
        ("Grounding pass rate (answers with facts)", f"{_ci(g['pass_rate'])} over {g['answers_checked']}"),
        ("Latency per question (mean / p50 / p95)", " / ".join("n/a" if lat[k] is None else f"{lat[k]:.0f} ms" for k in ("mean", "p50", "p95"))),
    ]


_SETS = (("original", "retrieval_only", "Original"), ("development", "retrieval_only_development", "Development"), ("heldout", "retrieval_only_heldout", "Held-out"))


def _columns(blocks: list[tuple[str, dict[str, Any] | None]]) -> str:
    """Rows of `_mode_rows` side by side, one column per phrasing set (a missing set shows "not run")."""
    present = [(label, block) for label, block in blocks if block]
    header = "| Measure | " + " | ".join(label for label, _ in blocks) + " |\n|---|" + "---|" * len(blocks)
    rows = {label: dict(_mode_rows(block)) for label, block in present}
    names = [name for name, _ in _mode_rows(present[0][1])]
    body = ["| " + name + " | " + " | ".join(rows[label][name] if label in rows else "not run" for label, _ in blocks) + " |" for name in names]
    return header + "\n" + "\n".join(body)


def _by_type(blocks: list[tuple[str, dict[str, Any] | None]]) -> list[str]:
    types = sorted({k for _, b in blocks if b for k in b["answerable"]["recall_by_fact_type"]})
    lines = ["| Fact type | " + " | ".join(f"{label}: n / recall" for label, _ in blocks) + " |", "|---|" + "---|" * len(blocks)]
    for k in types:
        cells = []
        for _, block in blocks:
            v = block["answerable"]["recall_by_fact_type"].get(k) if block else None
            cells.append("-" if v is None else f"{v['n']} / {100 * v['recall']:.1f} %")
        lines.append(f"| `{k}` | " + " | ".join(cells) + " |")
    return lines


def _phrasing_section(result: dict[str, Any]) -> list[str]:
    """The three phrasing sets on the same unseen (reporting-half) processes, new retrieval and the earlier one."""
    after = [(label, result.get(key)) for _, key, label in _SETS]
    legacy = result.get("baseline_legacy") or {}
    before = [(label, legacy.get(name)) for name, _, label in _SETS]
    out = [
        "Three disjoint sets of phrasings, all on the same reporting-half processes. **Original**: written together with the retrieval keys; "
        "the thresholds were tuned on its tuning-half questions. **Development**: the independently worded set of review 5, now seen by the "
        "developers and also used for tuning (so its numbers are optimistic). **Held-out**: written before the intent retrieval was built, "
        "never used for tuning or for choosing prototypes, evaluated once for the final report (`tests/evaluation/test_qa_phrasing_sets.py` "
        "asserts the three sets are disjoint and independent of every retrieval key; the held-out file's SHA-256 is in `eval/qa.json`).",
        "",
        "**Intent retrieval (current)**",
        "",
        _columns(after),
        "",
        f"**Earlier key-phrase retrieval, re-measured in this run on the same questions** ({result.get('legacy_thresholds', {})})",
        "",
        _columns(before),
        "",
        "Recall by fact type, intent retrieval (reporting half):",
        "",
        *_by_type(after),
        "",
        "Recall by fact type, earlier retrieval:",
        "",
        *_by_type(before),
        "",
        f"Questions per set: { {k: v['total'] for k, v in result['sample'].get('questions_by_phrasing_set', {}).items()} }; "
        f"held-out evaluations so far (this file): {result.get('heldout_runs', 0)}; held-out file SHA-256 `{result.get('heldout_sha256')}`.",
    ]
    return out


def _table(rows: list[tuple[str, str]]) -> str:
    return "\n".join(["| Measure | Value |", "|---|---|", *[f"| {k} | {v} |" for k, v in rows]])


def _successes(adv: dict[str, Any]) -> str:
    if not adv["successes"]:
        return "No attack succeeded."
    lines = ["| Category | Attack number | Breach |", "|---|---|---|"]
    lines += [f"| {s['category']} | {s['attack']} | `{s['breach']}` |" for s in adv["successes"][:40]]
    if len(adv["successes"]) > 40:
        lines.append(f"| … | … | {len(adv['successes']) - 40} more in `eval/qa.json` |")
    return "\n".join(lines)


def _attack_lines(result: dict[str, Any]) -> list[str]:
    out = []
    for _, key, label in _SETS:
        block = result.get(key)
        if not block:
            continue
        adv = block["adversarial"]
        out.append(
            f"Attacks, {label.lower()} set ({adv['distinct_attacks']} distinct): outcomes {adv['outcomes']}; answered with facts: "
            f"{adv.get('answered_with_facts', {}).get('count', 'n/a')} {adv.get('answered_with_facts', {}).get('by_category', '')}; "
            f"judgement questions without the fixed sentence: {adv.get('judgement_without_the_fixed_sentence', 'n/a')}. {_successes(adv)}"
        )
        out.append("")
    return out


def render_markdown(result: dict[str, Any]) -> str:
    sample, th = result["sample"], result["thresholds"]
    parts = [
        DOC_BEGIN,
        f"Generated by `veedor evaluate qa` (seed {result['seed']}, 2000 bootstrap resamples; intervals are 95 % percentile intervals over questions).",
        "",
        "**Design.** {p:,} processes were sampled at random (two thirds with a risk signal, one third without, plus every stored investigation); "
        "{q:,} questions were generated from the data by templates (answerable, with the expected fact ids known by construction; unanswerable; "
        "adversarial: {a} distinct attacks, each applied to two processes of the tuning half and three of the reporting half). The processes were split in halves by a hash of their identifier: "
        "the similarity floor and k were chosen on the **tuning half** ({tq:,} questions, {tp} processes) and every number below is for the "
        "**reporting half** ({rq:,} questions, {rp} processes).".format(
            p=sample["processes"], q=sample["questions_total"], a=sample["distinct_attacks"], tq=sample["questions_tuning_half"],
            tp=sample["processes_tuning_half"], rq=sample["questions_reporting_half"], rp=sample["processes_reporting_half"],
        ),
        "",
        f"**Chosen on the tuning half** (original and development phrasings of those processes; coordinate descent): "
        f"{ {k: th[k] for k in ('floor', 'k', 'lexical_weight', 'e_lo', 'e_hi', 'oos_margin', 'absent_margin', 'second_gap')} }, model floor {th['model_floor']} "
        f"(objective: mean over both sets of the answerable F1 and the abstention rate = {th['objective']}); the 12 candidates sent to a model contain every "
        f"expected fact in {100 * th['candidate_recall_tuning_half']:.1f} % of the answerable tuning questions.",
        "",
        "### Retrieval only (no model): three phrasing sets, before and after",
        "",
        *_phrasing_section(result),
        "",
        *_attack_lines(result),
    ]
    model = result.get("model")
    parts += ["", "### Model mode", ""]
    if not model or model.get("status") != "ran":
        parts.append("No model was configured for this run (a provider, a model name and a key are all needed): **model mode was not run**.")
    else:
        mm, same = model["model_mode"], model["retrieval_same_questions"]
        parts += [
            f"Model `{model['model']}` over {model['questions']} questions of the reporting half (about 60 answerable, 40 unanswerable and each attack once), "
            "**measured on the in-vocabulary phrasings only, with the earlier key-phrase retrieval ranking the candidates and gating the model** "
            "(not rerun since: cost); the same questions answered by retrieval only (also the earlier one) are shown for comparison.",
            "",
            "| Measure | Model | Retrieval only |",
            "|---|---|---|",
            *[f"| {a[0]} | {a[1]} | {b[1]} |" for a, b in zip(_mode_rows(mm), _mode_rows(same), strict=True)],
            "",
            f"Model calls {mm['model']['calls']}; tokens per call: {mm['model']['prompt_tokens_per_call']:.0f} prompt, {mm['model']['completion_tokens_per_call']:.0f} completion; "
            f"ids discarded for being outside the candidate set: {mm['model']['discarded_ids']}. Attack outcomes (model): {mm['adversarial']['outcomes']}. {_successes(mm['adversarial'])}",
        ]
    parts += [DOC_END]
    return "\n".join(parts)


def update_docs(doc_path: Path, markdown: str) -> None:
    """Replace the generated block, or append it when the markers are absent."""
    text = doc_path.read_text(encoding="utf-8") if doc_path.is_file() else ""
    pattern = re.compile(re.escape(DOC_BEGIN) + r".*?" + re.escape(DOC_END), re.DOTALL)
    if pattern.search(text):
        doc_path.write_text(pattern.sub(lambda _: markdown, text), encoding="utf-8")
    else:
        doc_path.write_text(text.rstrip("\n") + "\n\n## Question answering (generated)\n\n" + markdown + "\n", encoding="utf-8")


def qa_block_of(text: str) -> str | None:
    match = re.search(re.escape(DOC_BEGIN) + r".*?" + re.escape(DOC_END), text, re.DOTALL)
    return match.group(0) if match else None
