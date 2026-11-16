# ruff: noqa: E501  (long prose lines in the document template)
"""Render docs/EVALUATION.md and small CSVs from the harness JSON.

Every number in the document is read from the JSON dictionaries. The only text written by hand is
method description and caveats, and it contains no figures; sentences whose wording depends on a
result (for example "the interval includes 0.5") are chosen by code from the numbers.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

Interval = dict[str, float | None]

SCORE_LABELS = {
    "A": "Held-out score A",
    "B": "Held-out score B",
    "C": "Score C (time-aware status kept)",
    "full": "Full risk score (contains the label; reference only)",
}
AGG_LABELS = {"mean": "supplier mean", "max": "supplier max", "share": "share of processes with a signal"}
BASELINE_LABELS = {
    "amount": "Baseline: total amount awarded",
    "n_processes": "Baseline: number of processes won",
}
SIGNAL_NOTE = {
    "label": "label (not a predictor)",
    "context": "context only (weight 0, outside the score)",
    "kept_in_variant_C": "excluded in A and B, kept in C (time-aware)",
    "checked_in_variant_B": "in A, excluded from B",
    "in_heldout": "",
}


def _fmt(value: float | None, digits: int) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def ci(i: Interval, digits: int = 3) -> str:
    """Estimate with its 95 % interval."""
    if i["low"] is None or i["high"] is None:
        return _fmt(i["estimate"], digits)
    return f"{_fmt(i['estimate'], digits)} ({_fmt(i['low'], digits)} to {_fmt(i['high'], digits)})"


def pct(i: Interval, digits: int = 1) -> str:
    def p(v: float | None) -> str:
        return "n/a" if v is None else f"{v * 100:.{digits}f}%"

    if i["low"] is None or i["high"] is None:
        return p(i["estimate"])
    return f"{p(i['estimate'])} ({p(i['low'])} to {p(i['high'])})"


def table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def score_label(key: str) -> str:
    name, _, agg = key.partition(":")
    if name == "baseline":
        return BASELINE_LABELS[agg]
    if name == "anomaly":
        return f"anomaly_score, {agg}"
    return f"{SCORE_LABELS[name]}, {AGG_LABELS[agg]}"


def position(i: Interval, reference: float = 0.5) -> str:
    """Where an interval sits relative to a reference value, in words chosen by the numbers."""
    low, high = i["low"], i["high"]
    if low is None or high is None:
        return "has no interval"
    if low > reference:
        return f"lies entirely above {reference:g}"
    if high < reference:
        return f"lies entirely below {reference:g}"
    return f"includes {reference:g}"


def scores_table(analysis: dict[str, Any]) -> str:
    perm = analysis.get("permutation_p_auc", {})
    rows = []
    for key, m in analysis["scores"].items():
        rows.append(
            [
                score_label(key),
                ci(m["auc"]),
                f"{perm[key]:.3f}" if key in perm else "",
                ci(m["average_precision"], 4),
                ci(m["lift_top_1"], 2),
                ci(m["lift_top_5"], 2),
                ci(m["lift_top_10"], 2),
            ]
        )
    headers = [
        "Score",
        "ROC-AUC",
        "Permutation p",
        "Average precision",
        "Lift top 1%",
        "Lift top 5%",
        "Lift top 10%",
    ]
    if not perm:
        headers.remove("Permutation p")
        rows = [r[:2] + r[3:] for r in rows]
    return table(headers, rows)


def paired_table(analysis: dict[str, Any]) -> str:
    rows = []
    for key, v in analysis["paired_differences"].items():
        left, right = key.split(" - ")
        rows.append(
            [f"{score_label(left)} minus {score_label(right)}", ci(v["auc"]), ci(v["average_precision"], 4)]
        )
    return table(["Difference (paired bootstrap)", "AUC difference", "AP difference"], rows)


def plain_reading(bt: dict[str, Any]) -> str:
    """One computed sentence on whether the held-out aggregates separate from chance."""
    prim, rob = bt["primary"], bt["robustness"]
    keys = [f"{v}:{a}" for v in ("A", "B", "C") for a in ("mean", "max", "share")]
    above = [k for k in keys if prim["scores"][k]["auc"]["low"] > 0.5]
    at_or_below = [k for k in keys if prim["scores"][k]["auc"]["estimate"] <= 0.5]
    conc = rob["stratified_concordance"]
    if not above and conc["low"] <= 0.5:
        verdict = (
            "None of the held-out aggregates has an AUC interval entirely above 0.5, and neither does the "
            "method-year matched comparison. In plain terms: with this label and this sample, the indicators "
            "show no detectable ability to single out the listed suppliers."
        )
    elif above:
        verdict = (
            f"Aggregates with an AUC interval entirely above 0.5: {', '.join(f'`{k}`' for k in above)}. "
            "Read them against the matched comparison and the buyer concentration below before drawing conclusions."
        )
    else:
        verdict = "No aggregate has an AUC interval entirely above 0.5, but the matched comparison differs; see below."
    if conc["high"] is not None and conc["high"] < 0.5:
        verdict += (
            " The method-year matched comparison is entirely below 0.5: the processes of listed suppliers carry, if anything, "
            "fewer held-out signals than comparable processes of unlabelled suppliers."
        )
    return (
        f"{verdict} {len(at_or_below)} of the {len(keys)} held-out aggregates have an AUC point estimate at or below 0.5. "
        "A wide interval means the data cannot rule out a modest real effect either; it is an absence of evidence, not evidence of absence."
    )


def headline(bt: dict[str, Any]) -> str:
    key = bt["meta"]["headline"]
    a = bt["primary"]
    m = a["scores"][key]
    amount = a["scores"]["baseline:amount"]
    diff = a["paired_differences"][f"{key} - baseline:amount"]["auc"]
    full = a["scores"]["full:mean"]["auc"]
    perm = a["permutation_p_auc"][key]
    prevalence = a["prevalence"]
    return (
        f"On the pre-specified headline (`{key}`: held-out score A, supplier mean, companies only), the ROC-AUC "
        f"is {ci(m['auc'])} over {a['n_positives']} listed suppliers and {a['n_unlabelled']:,} unlabelled "
        f"suppliers; the interval {position(m['auc'])}. The one-sided permutation p-value against "
        f'"no relation to the label" is {perm:.3f}. Average precision is {ci(m["average_precision"], 4)} '
        f"against a prevalence of {prevalence:.4f}, and lift in the top 5% is {ci(m['lift_top_5'], 2)}.\n\n"
        f'The naive baseline "total amount awarded" has AUC {ci(amount["auc"])}; the paired difference '
        f"(held-out mean minus amount) is {ci(diff)}, which {position(diff, 0.0)}. "
        + leakage_sentence(full, m["auc"])
    )


def leakage_sentence(full: Interval, held_out: Interval) -> str:
    if abs(full["estimate"] - held_out["estimate"]) < 0.005:
        return (
            f"The full production score now gives the same AUC ({ci(full)}) because the label-derived signal fires "
            "only for listings notified on or before the process date, so it almost never fires on the supplier-level "
            "positives; the leakage that inflated this figure in earlier runs (see Analysis history) is gone from the production score."
        )
    return (
        f"For contrast, the full risk score, which contains the label itself, reaches AUC {ci(full)}: "
        "that figure is leakage, not skill, and is shown only to make the size of the leakage visible."
    )


def signal_table(block: dict[str, Any]) -> str:
    rows = []
    for code, s in block["signals"].items():
        rows.append(
            [
                f"`{code}`",
                SIGNAL_NOTE[s["role"]],
                f"{s['fired_positives']}",
                pct(s["rate_positives"]),
                pct(s["rate_unlabelled"], 2),
                ci(s["ratio"], 2) if s["ratio"]["estimate"] is not None else "n/a",
            ]
        )
    return table(
        ["Signal", "Role", "Fired in positives' processes", "Rate, positives", "Rate, unlabelled", "Ratio"],
        rows,
    )


def signal_reading(block: dict[str, Any]) -> str:
    above, spans, never = [], [], []
    for code, s in block["signals"].items():
        if s["role"] in ("label", "kept_in_variant_C", "context"):
            continue
        r = s["ratio"]
        if s["fired_positives"] == 0:
            never.append(code)
        elif r["low"] is not None and r["low"] > 1:
            above.append(code)
        else:
            spans.append(code)
    fmt = lambda xs: ", ".join(f"`{x}`" for x in xs) if xs else "none"  # noqa: E731
    return (
        f"Among the signals that are not excluded: ratio interval entirely above 1: {fmt(above)}. "
        f"Ratio interval that includes 1 or lies below it: {fmt(spans)}. "
        f"Never fired in the positives' processes (uninformative at this sample size, not evidence of absence): {fmt(never)}."
    )


def coverage_sections(cov: dict[str, Any]) -> str:
    out = [
        f"{cov['n_with_any_signal']:,} of {cov['n_processes']:,} processes "
        f"({cov['n_with_any_signal'] / cov['n_processes']:.1%}) carry at least one signal.",
        "",
        "### Context signals (weight 0, outside the score)",
        "",
        table(
            ["Signal", "Processes"],
            [[f"`{c}`", f"{n:,}"] for c, n in cov["context_signals"]["fired"].items()],
        )
        + f"\n\n{cov['context_signals']['n_with_any_context']:,} processes carry a context signal; "
        f"{cov['context_signals']['n_with_context_and_risk']:,} of them also carry a risk signal.",
        "",
        "### By method group",
        "",
        table(
            [
                "Method group",
                "Processes",
                "With any signal",
                "Share (all signals)",
                "Share (held-out A signals)",
            ],
            [
                [
                    str(r["key"]),
                    f"{r['n_processes']:,}",
                    f"{r['with_any_signal']:,}",
                    f"{r['share_any']:.1%}",
                    f"{r['share_any_held_out']:.1%}",
                ]
                for r in cov["by_method_group"]
            ],
        ),
        "",
        "### By year",
        "",
        table(
            ["Year", "Processes", "With any signal", "Share (all signals)", "Share (held-out A signals)"],
            [
                [
                    str(r["key"]),
                    f"{r['n_processes']:,}",
                    f"{r['with_any_signal']:,}",
                    f"{r['share_any']:.1%}",
                    f"{r['share_any_held_out']:.1%}",
                ]
                for r in cov["by_year"]
            ],
        ),
        "",
        "### Signals fired",
        "",
        table(["Signal", "Processes"], [[f"`{c}`", f"{n:,}"] for c, n in cov["signals_fired"].items()]),
        "",
        "### Co-occurrence (processes where both signals fired; the diagonal is the total per signal)",
        "",
    ]
    codes = cov["cooccurrence"]["codes"]
    counts = cov["cooccurrence"]["counts"]

    def cell(i: int, j: int) -> str:
        a, b = codes[i], codes[j]
        v = counts.get(f"{a}|{b}", counts.get(f"{b}|{a}"))
        return f"{v:,}"

    out.append(
        table(
            ["Signal"] + [str(j + 1) for j in range(len(codes))],
            [[f"{i + 1}. `{c}`"] + [cell(i, j) for j in range(len(codes))] for i, c in enumerate(codes)],
        )
    )
    for name, key in (
        ("Risk score (all signals)", "risk_score_distribution"),
        ("Held-out score A", "held_out_score_distribution"),
    ):
        d = cov[key]
        out += [
            "",
            f"### Distribution: {name}",
            f"Share of processes at 0: {d['share_zero']:.1%}; maximum {d['max']:g}; quantiles "
            + ", ".join(f"p{float(q) * 100:g} = {v:g}" for q, v in d["quantiles"].items())
            + ".",
            "",
            table(
                ["Score", "Processes", "Share"],
                [
                    [f"{h['score']:g}", f"{h['n_processes']:,}", f"{h['n_processes'] / d['n_processes']:.3%}"]
                    for h in d["histogram"]
                ],
            ),
        ]
    return "\n".join(out)


def anomaly_section(anomaly: dict[str, Any]) -> str:
    head = f"{anomaly['description']}: {anomaly['n_positives']} positives, {anomaly['n_unlabelled']:,} unlabelled."
    if not anomaly["scores"]:
        return head
    return (
        f"{head} The anomaly score exists only for processes with enough numeric features, so this universe is smaller. "
        f"The AUC interval of the supplier mean {position(anomaly['scores']['anomaly:mean']['auc'])}.\n\n"
        + scores_table(anomaly)
    )


def leave_one_out_section(loo: dict[str, Any]) -> str:
    rows = []
    for variant, aggs in loo["variants"].items():
        for agg, r in aggs.items():
            rows.append(
                [
                    f"{SCORE_LABELS[variant]}, {AGG_LABELS[agg]}",
                    f"{r['min_auc']:.3f}",
                    f"{r['min_buyer']} ({r['min_n_positives']} positives left)",
                    f"{r['max_auc']:.3f}",
                    f"{r['max_buyer']} ({r['max_n_positives']} positives left)",
                ]
            )
    return (
        f"Each of the {loo['n_buyers_dropped_in_turn']} buyers where a positive won is removed in turn (every process of that buyer, "
        "for positives and unlabelled suppliers alike) and the AUC is recomputed. Point estimates only; the range shows whether one buyer drives the result.\n\n"
        + table(["Score", "Lowest AUC", "Buyer removed", "Highest AUC", "Buyer removed"], rows)
    )


def conclusion_changed(bt: dict[str, Any]) -> str:
    entries = bt["history"]
    if len(entries) < 2:
        return ""
    first, last = entries[0]["headline_auc"], entries[-1]["headline_auc"]
    same = position(first) == position(last)
    return (
        f"Across {len(entries)} runs after rule changes the headline AUC went from {_fmt(first['estimate'], 3)} to {_fmt(last['estimate'], 3)}; "
        + ("the conclusion did not change." if same else "the conclusion changed (see Analysis history).")
    )


def history_section(bt: dict[str, Any]) -> str:
    entries = bt["history"]
    rows = [
        [
            str(i + 1),
            e["generated_at"],
            e["note"],
            ci(e["headline_auc"]),
            f"{e['n_positives']} / {e['n_unlabelled']:,}",
        ]
        for i, e in enumerate(entries)
    ]
    last = entries[-1]["headline_auc"]
    if len(entries) > 1:
        first, prev = entries[0]["headline_auc"], entries[-2]["headline_auc"]
        moved = (
            f"The headline AUC moved from {_fmt(first['estimate'], 3)} (run 1) to {_fmt(last['estimate'], 3)} (latest run), "
            f"and from {_fmt(prev['estimate'], 3)} in the previous run. "
            f"In run 1 the interval {position(first)}; in the latest run it {position(last)}. "
            + (
                "The qualitative conclusion did not change."
                if position(first) == position(last)
                else "The qualitative conclusion changed."
            )
        )
    else:
        moved = "This is the first recorded run."
    return "\n".join(
        [
            "Each row is one back-test run on the same labels (`eval/history.json`, appended by `veedor evaluate backtest`). "
            "Development runs with a smaller bootstrap made while the harness was being written used the first marts and are not listed.",
            "",
            table(
                ["Run", "Date-time", "What changed", "Headline AUC (95% CI)", "Positives / unlabelled"], rows
            ),
            "",
            moved,
            "",
            "The rule changes were made for correctness reasons found by review, and, as recorded by the project team, no rule was changed in order to move this metric. "
            "Even so, adjusting rules after looking at a metric on the same labels is a source of optimism: the labels are no longer a clean, independent test of the final rules. "
            "Readers should treat the latest figure as a descriptive check and not as an unbiased estimate of performance, and the more so the better it looks.",
        ]
    )


def summary_section(bt: dict[str, Any]) -> str:
    """Plain-language summary; every figure comes from the JSON."""
    prim = bt["primary"]
    key = bt["meta"]["headline"]
    m = prim["scores"][key]["auc"]
    c = prim["scores"]["C:mean"]["auc"]
    return "\n".join(
        [
            "## Summary for non-specialists",
            "",
            f"**What was tested.** Veedor gives each public contract a risk score from simple rules (for example, a single bidder). "
            f'The only official outside list we could use is the SRI\'s published list of "empresas fantasmas" (shell companies): '
            f"{bt['labels']['n_listed_rucs']:,} tax numbers, of which {prim['n_positives']} are companies that won public contracts. "
            f"We asked whether the score ranks those companies higher than the other {prim['n_unlabelled']:,} contract-winning companies, "
            "after removing the rules that use the list itself.",
            "",
            f"**Result.** Chance level is an AUC of 0.5; the score reached {ci(m)}, and the interval {position(m)}. "
            f"Keeping the time-aware inactive-supplier rule gives {ci(c)}, which {position(c)}. "
            "The available evidence does not show that the score singles out the listed suppliers. "
            + conclusion_changed(bt),
            "",
            "**What it means in practice.** With so few listed companies the test cannot rule out a modest real effect, and being on the list "
            "is not the same as a problematic contract. The indicators should be read as descriptive transparency measures that point to atypical "
            "features of a process for a human to look at. They are not validated predictors of wrongdoing, and a high score is not an accusation.",
        ]
    )


def positives_summary_text(summary: dict[str, Any], n_positives: int) -> str:
    """Listed suppliers appear only as counts; buyers are anonymised by rank elsewhere in the document."""
    return (
        f"Of the {n_positives} positive companies, {summary['n_with_zero_held_out_mean']} have a held-out mean score of zero and "
        f"{summary['n_with_positive_held_out_mean']} have a positive one. They won between {summary['n_processes_min']} and "
        f"{summary['n_processes_max']} processes each (median {summary['n_processes_median']:g}). "
        "No supplier or buyer is named in this document: buyers are labelled by rank of positive processes."
    )


def render(bt: dict[str, Any], cov: dict[str, Any]) -> str:
    meta, labels, prim = bt["meta"], bt["labels"], bt["primary"]
    comp, nat = labels["by_kind"]["company"], labels["by_kind"]["natural_person"]
    temporal, rob, buyers, chk = (
        bt["temporal"],
        bt["robustness"],
        bt["buyer_concentration"],
        bt["size_signal_check"],
    )
    all_s, all_t, anomaly = bt["all_suppliers"], bt["all_suppliers_temporal"], bt["anomaly"]
    sig_all, sig_nc = bt["per_signal"]["all_processes"], bt["per_signal"]["non_catalogue"]
    unl_catalogue_share = 1 - sig_nc["n_processes_unlabelled"] / sig_all["n_processes_unlabelled"]
    pos_catalogue = sig_all["n_processes_positives"] - sig_nc["n_processes_positives"]
    variants = "\n".join(
        f"- **{k}**: {v['description']} (excluded: {', '.join(f'`{c}`' for c in v['excluded'])})"
        for k, v in meta["variants"].items()
    )
    weights = table(["Signal", "Weight"], [[f"`{c}`", f"{w:g}"] for c, w in meta["weights"].items()])
    temporal_same = temporal["scores"] == prim["scores"] or comp["processes_on_or_after_notification"] == 0
    after_note = (
        f"No award of a positive company is dated on or after its notification date "
        f"({comp['processes_before_notification']} of {comp['n_processes']} processes are before it), so the temporal filter removes nothing for companies "
        f"and all {temporal['n_positives']} positives survive. The result is therefore identical to the main analysis."
        if temporal_same
        else f"{temporal['n_positives']} of {prim['n_positives']} positive companies survive the filter."
    )
    check_text = (
        f"{chk['n_fired_on_positive_company_processes']} processes of positive companies fired `CONTRACT_VS_COMPANY_SIZE`; "
        f"{chk['n_fired_awarded_on_or_after_notification']} of them were awarded on or after the notification date, and "
        f"{chk['n_fired_with_revenue_year_at_or_after_notification_year']} used a revenue year at or after the notification year. "
        f"The signal needs a positive revenue row in the Superintendencia data: {chk['share_positives_with_positive_revenue_row']:.1%} of positive companies "
        f"({chk['n_positive_companies']}) have one, against {chk['share_unlabelled_with_positive_revenue_row']:.1%} of unlabelled companies "
        f"({chk['n_unlabelled_companies']:,})."
    )
    sc = bt["status_signal_check"]
    status_text = (
        f"The signal fires {sc['n_firings']:,} times in total; {sc['n_firings_on_positive_processes']} of those firings are on processes won by "
        f"listed suppliers ({sc['n_firings_on_positive_company_processes']} on companies), and {sc['n_firings_on_positive_processes_after_notification']} of "
        "them are on awards dated on or after the SRI notification date. "
        + (
            "Because it fires on no positive process, variant C is numerically identical to variant A for the positives and the status signal cannot be leaking the label here."
            if sc["n_firings_on_positive_processes"] == 0
            else "Firings on positives mean the signal can still carry information about the listing, so C should be read with that caveat."
        )
    )
    parts = [
        "# Evaluation of the risk indicators",
        "",
        f"Generated by `veedor evaluate report` from `eval/backtest.json` (run {meta['generated_at']}, seed {meta['seed']}, "
        f"{meta['n_boot']:,} bootstrap replicates) and `eval/coverage.json`. Do not edit by hand: every number below is read from those files.",
        "",
        "Veedor reports risk indicators, never accusations. This document asks a narrower question: "
        "do the indicators carry any measurable signal against the only external label available?",
        "",
        summary_section(bt),
        "",
        "## Headline",
        "",
        headline(bt),
        "",
        plain_reading(bt),
        "",
        "## Analysis history",
        "",
        history_section(bt),
        "",
        "## What this does and does not show",
        "",
        "**It shows** how a score built from the indicators ranks suppliers that the SRI later published as "
        '"empresas fantasmas" relative to all other awarded companies, once the signals that encode the label are removed, '
        "and how wide the uncertainty is with so few positives.",
        "",
        "**It does not show** that any indicator detects improper procurement. The label is a tax-administration "
        "classification of a company, not a finding about a contract. A score that fails to separate these companies says "
        "little about whether it flags atypical processes in general, and a score that succeeds would not prove wrongdoing either. "
        "There is no labelled set of proven problem contracts in the open data, so predictive validity for the purpose the "
        "indicators serve (prioritising processes for human review) is **not established** by this evaluation.",
        "",
        "## Method",
        "",
        "### Data and label",
        "",
        f"- Processes scored: {meta['n_processes']:,}. Signals are read from `process_signals`; the check that rebuilt flags equal the `signal_codes` list of `process_scores` found "
        f"{meta['consistency']['processes_with_flag_mismatch']} mismatching processes.",
        f'- Label: the SRI list of "empresas fantasmas" ({labels["n_listed_rucs"]:,} RUCs). {labels["n_suppliers_with_award"]} of them won at least one process as the '
        f"process winner (the supplier with the largest award in `process_scores`): {comp['n_suppliers_with_award']} companies "
        f"({comp['n_processes']} processes) and {nat['n_suppliers_with_award']} natural persons ({nat['n_processes']} processes).",
        "- Positive-unlabelled setting: a supplier that is not listed is **unlabelled**, not known to be clean. Some unlabelled suppliers may "
        "resemble the listed ones, which pushes every metric toward chance.",
        f"- **Primary universe: companies only** (RUC third digit 9): {prim['n_positives']} positives against {prim['n_unlabelled']:,} unlabelled "
        "companies. Natural persons and companies differ in which signals can fire at all (for example the company-size signal needs "
        "Superintendencia financials), so mixing them would make the comparison unlike-for-like. A sensitivity analysis with both kinds is reported separately.",
        "",
        "### Leakage control",
        "",
        "`GHOST_COMPANY_LIST` is the label and is always removed. `SUPPLIER_NOT_ACTIVE` is time-aware in the current marts (it fires only when the "
        "suspension came before the process date), but it is still derived from SRI status, which can be a consequence of being listed. "
        "The headline variant A removes it as a precaution; variant C keeps it so the effect of that choice is visible. "
        "The score is recomputed from "
        "`process_signals` with the production weights (sum of the weights of distinct fired signals, capped at 100):",
        "",
        variants,
        "",
        "Weights (uncalibrated judgement calls):",
        "",
        weights,
        "",
        "`CONTRACT_VS_COMPANY_SIZE` now compares the award with the latest revenue year strictly before the award year, so the revenue it uses always predates the award. "
        "Evidence on whether it could still be affected by the listing (a check, not a proof; the same-year variant is a context signal and is not scored):",
        "",
        check_text,
        "",
        "Evidence on `SUPPLIER_NOT_ACTIVE` (can it still leak?):",
        "",
        status_text,
        "",
        "All variants are reported. Variant A is the headline.",
        "",
        "### Supplier-level back-test",
        "",
        "Each supplier's held-out process scores are aggregated three ways: mean, max and the share of its processes with at least one "
        "signal. Suppliers are ranked by each aggregate. Metrics: ROC-AUC and average precision (ties are handled as blocks; ties at a "
        "cut-off are split proportionally), and lift in the top 1%, 5% and 10% (precision in the top fraction divided by the base rate). "
        "Confidence intervals are percentile intervals from a supplier-level bootstrap, stratified by label so that every replicate keeps "
        "the same number of positives. Each replicate re-draws suppliers, so the dependence between the processes of one supplier is respected. "
        f"The permutation p-value is the share of {meta['n_permutations']:,} random labelings with the same number of positives whose AUC is at least the observed one.",
        "",
        'The max and share aggregates favour suppliers with many processes; the baseline "number of processes won" is reported to make that visible. '
        "The aggregates take few distinct values, so large blocks of suppliers are tied (most at zero) and lift at different cut-offs can coincide. "
        "A random ranking has average precision equal to the prevalence.",
        "",
        "### Temporal honesty",
        "",
        "Awards made after the SRI notification date are not predictive evidence (the signals could already reflect the listing). "
        "The temporal analysis keeps only each positive's processes dated before its notification date, and drops positives with no "
        "notification date. The award date is `first_award_date`, falling back to `date_signed`, then `release_date`. Unlabelled suppliers are not restricted.",
        "",
        "### Per-signal view, baselines, robustness",
        "",
        "Per signal: the rate of firing among the processes of positives against the processes of unlabelled suppliers, their ratio, and "
        "intervals from the same supplier-level bootstrap. Baselines: random ranking (AUC 0.5, lift 1, average precision equal to prevalence), "
        "total amount awarded, and number of processes won. Robustness: each positive process is compared with unlabelled company-won "
        "processes of the same method (all catalogue conventions are one stratum) and the same year, giving the stratified concordance "
        "(probability that a positive process outscores a same-stratum unlabelled one, ties counting half; 0.5 means no difference) and "
        "observed versus expected mean score and any-signal share. Only positives are resampled there; the unlabelled strata are held fixed.",
        "",
        "## Results",
        "",
        "### Main back-test (companies, all awards)",
        "",
        f"Positives: {prim['n_positives']}. Unlabelled: {prim['n_unlabelled']:,}. Prevalence: {prim['prevalence']:.5f}. "
        "Random ranking: AUC 0.5, lift 1.",
        "",
        scores_table(prim),
        "",
        "Paired differences against the amount baseline:",
        "",
        paired_table(prim),
        "",
        "### Temporal back-test",
        "",
        after_note,
        "",
        f"Positives surviving: {temporal['n_positives']}.",
        "",
        scores_table(temporal),
        "",
        "### Sensitivity: companies and natural persons together (not like-for-like)",
        "",
        f"All awards: {all_s['n_positives']} positives, {all_s['n_unlabelled']:,} unlabelled.",
        "",
        scores_table(all_s),
        "",
        f"Positives before notification only: {all_t['n_positives']} positives surviving, {all_t['n_unlabelled']:,} unlabelled.",
        "",
        scores_table(all_t),
        "",
        "### Anomaly score alone",
        "",
        anomaly_section(anomaly),
        "",
        "### Per-signal view (all processes)",
        "",
        f"Positives' processes: {sig_all['n_processes_positives']} (from {sig_all['n_positive_suppliers']} suppliers); unlabelled: {sig_all['n_processes_unlabelled']:,}. "
        f"{pos_catalogue} of the positives' processes are catalogue purchases, against {unl_catalogue_share:.1%} of the unlabelled processes. "
        "Because many signals cannot fire on catalogue purchases, the all-process rates mix signal behaviour with method mix.",
        "",
        signal_table(sig_all),
        "",
        "### Per-signal view (non-catalogue processes only)",
        "",
        f"Positives' processes: {sig_nc['n_processes_positives']}; unlabelled: {sig_nc['n_processes_unlabelled']:,}.",
        "",
        signal_table(sig_nc),
        "",
        signal_reading(sig_nc),
        "",
        "The two rows marked as label and as consequence of listing are shown to illustrate the leakage; they are not evidence that the signals work.",
        "",
        "### Robustness: matched on method and year",
        "",
        f"{rob['n_positive_processes_used']} positive processes in {rob['n_strata_with_positives']} method-year strata "
        f"({rob['n_positive_suppliers']} suppliers); {rob['n_positive_processes_dropped_no_stratum']} dropped for lack of unlabelled peers.",
        "",
        table(
            ["Quantity", "Estimate (95% CI)"],
            [
                ["Stratified concordance (0.5 = no difference)", ci(rob["stratified_concordance"])],
                ["Mean held-out score, positives' processes", ci(rob["mean_score_observed"], 2)],
                ["Mean held-out score expected from same strata", ci(rob["mean_score_expected"], 2)],
                ["Observed / expected mean score", ci(rob["mean_score_ratio"], 2)],
                ["Share with any held-out signal, positives", pct(rob["any_signal_observed"])],
                ["Share expected from same strata", pct(rob["any_signal_expected"])],
                ["Observed / expected share", ci(rob["any_signal_ratio"], 2)],
            ],
        ),
        "",
        f"The concordance interval {position(rob['stratified_concordance'])}. "
        "Matching on method and year does not by itself control for the buyer; see the next section.",
        "",
        "### Leave-one-buyer-out",
        "",
        leave_one_out_section(bt["leave_one_buyer_out"]),
        "",
        "### Concentration of positives by buyer",
        "",
        f"{buyers['n_positive_processes']} positive processes span {buyers['n_distinct_buyers']} buyers; the effective number of buyers "
        f"(inverse Herfindahl) is {buyers['effective_n_buyers']:.1f}. {buyers['positive_suppliers_sharing_a_buyer']} of {buyers['n_positive_suppliers']} positive suppliers "
        "share at least one buyer with another positive supplier. Positives that won at the same buyer are not independent observations "
        "(same procurement staff, same practices, possibly the same relationship), so the supplier-level intervals above are, if anything, "
        "optimistic about how much independent information the positives carry.",
        "",
        table(
            ["Buyer (anonymised)", "Positive processes", "Share of positive processes", "Positive suppliers"],
            [
                [b["buyer"], str(b["n_processes"]), f"{b['share']:.1%}", str(b["n_positive_suppliers"])]
                for b in buyers["top_buyers"]
            ],
        ),
        "",
        "### Listed suppliers (counts only)",
        "",
        positives_summary_text(prim["positives_summary"], prim["n_positives"]),
        "",
        "## Descriptive coverage (no labels)",
        "",
        coverage_sections(cov),
        "",
        "## Limitations",
        "",
        "- **Positive-unlabelled labels.** Unlisted suppliers are unlabelled, not clean; contamination biases every metric toward chance.",
        f"- **Very few positives.** {prim['n_positives']} positive companies. The intervals are wide and a null result cannot be separated from a weak real effect. Metrics such as lift in the top 1% rest on a handful of suppliers at most.",
        "- **The label is not procurement wrongdoing.** The SRI classification concerns tax-reporting behaviour of a company. It may correlate with contract risk or not.",
        "- **Uncalibrated weights.** The weights are judgement calls; nothing here tunes them, and a different weighting could rank differently.",
        "- **Survivorship.** Only listed suppliers that won a process in the open data can be positives. Suppliers that were listed before ever winning, or whose awards are missing, are invisible.",
        "- **Current-status leakage.** `SUPPLIER_NOT_ACTIVE` uses the status in a 2026 file. It is excluded here, but other registry-derived fields may carry similar hindsight.",
        "- **Contract-size signal.** The check above is limited to what the data can show; the variant B result is reported so the reader can see whether the conclusion depends on it.",
        "- **Emergency procurement is missing** from the open data, and it is where much documented concern lies. Indicators are untested there.",
        "- **Aggregation choices.** Supplier-level aggregates favour suppliers with many processes (max, share) and can hide single flagged processes (mean); none of them is the unit analysts review.",
        "- **Winner attribution.** A process's winner is the supplier with the largest award; co-awardees are not evaluated.",
        "",
    ]
    return "\n".join(parts)


def summary_text(bt: dict[str, Any]) -> str:
    prim = bt["primary"]
    lines = [
        f"Positives (companies): {prim['n_positives']}; unlabelled: {prim['n_unlabelled']:,}; "
        f"listed RUCs with an award, all kinds: {bt['labels']['n_suppliers_with_award']}",
        f"Temporal filter: {bt['temporal']['n_positives']} company positives survive",
        "ROC-AUC (95% CI), primary analysis:",
    ]
    for key, m in prim["scores"].items():
        lines.append(f"  {score_label(key)}: {ci(m['auc'])}; lift top 5% {ci(m['lift_top_5'], 2)}")
    rob = bt["robustness"]
    lines.append(f"Matched on method-year, stratified concordance: {ci(rob['stratified_concordance'])}")
    a = bt["anomaly"]["scores"]["anomaly:mean"]["auc"]
    lines.append(f"anomaly_score (supplier mean) AUC: {ci(a)}")
    return "\n".join(lines)


def write_csvs(bt: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "backtest_scores.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["analysis", "score", "metric", "estimate", "ci_low", "ci_high"])
        for name in ("primary", "temporal", "all_suppliers", "all_suppliers_temporal", "anomaly"):
            for key, metrics in bt[name]["scores"].items():
                for metric, i in metrics.items():
                    w.writerow([name, key, metric, i["estimate"], i["low"], i["high"]])
    with (out_dir / "backtest_per_signal.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "scope",
                "signal",
                "role",
                "fired_positives",
                "fired_unlabelled",
                "rate_pos",
                "rate_unl",
                "ratio",
                "ratio_low",
                "ratio_high",
            ]
        )
        for scope, block in bt["per_signal"].items():
            for code, s in block["signals"].items():
                w.writerow(
                    [
                        scope,
                        code,
                        s["role"],
                        s["fired_positives"],
                        s["fired_unlabelled"],
                        s["rate_positives"]["estimate"],
                        s["rate_unlabelled"]["estimate"],
                        s["ratio"]["estimate"],
                        s["ratio"]["low"],
                        s["ratio"]["high"],
                    ]
                )


def write_coverage_csvs(cov: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("by_method_group", "by_year"):
        with (out_dir / f"coverage_{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["key", "n_processes", "with_any_signal", "share_any", "share_any_held_out"])
            for r in cov[name]:
                w.writerow(
                    [
                        r["key"],
                        r["n_processes"],
                        r["with_any_signal"],
                        r["share_any"],
                        r["share_any_held_out"],
                    ]
                )
