"""The four specialists: one objective, an allow-list of tools and a step budget each.

A specialist never sees a string from a tool as an instruction. It runs an ordered list of enumerated
actions; each action resolves its target from the pack, calls one tool through `ToolRunner`, and
converts the validated result into typed facts. A failed call yields a fact with that outcome and
nothing else: no value, no guess.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from veedor.agents.investigation import targets
from veedor.agents.investigation.tools import RunBudget, ToolOutput, ToolRunner
from veedor.domain.dossier.models import (
    AuditFacts,
    CompanyFinancialsFacts,
    CompanyRegistryFacts,
    EnquiriesFacts,
    EvidencePack,
    PairHistoryFacts,
    SimilarPurchasesFacts,
    TaxRegistryLiveFacts,
)
from veedor.domain.investigation import convert
from veedor.domain.investigation.policies import Action
from veedor.domain.investigation.results import (
    Catalogue,
    CompaniaInfo,
    EnquirySummary,
    Financials,
    PairAwards,
    ReportsFile,
    SimilarSummary,
    SriRucInfo,
)

KeyIndexProvider = Callable[[], dict[str, frozenset[str]]]


@dataclass
class SpecialistContext:
    pack: EvidencePack
    runner: ToolRunner
    budget: RunBudget
    today: date
    key_index: KeyIndexProvider | None = None
    findings: dict[str, Any] = field(default_factory=dict)
    scratch: dict[str, Any] = field(default_factory=dict)
    failed_actions: list[str] = field(default_factory=list)  # actions that ended in a transient failure


Handler = Callable[[SpecialistContext], None]


def _status_facts(model: type, output: ToolOutput, **extra: Any) -> Any:
    """A facts object that records only the outcome (failure, skip or not-found), no values."""
    call = output.call
    if call.outcome == "ok":  # the source answered "no record"
        return model(outcome="ok", found=False, **extra)
    return model(outcome=call.outcome, **extra)


def _flag_out_of_range(output: ToolOutput, facts: Any) -> None:
    """Record in the tool log that a value of this result was rejected as implausible."""
    if getattr(facts, "out_of_range", None):
        output.call.reason = "out_of_range"


def _mark(ctx: SpecialistContext, action: Action, output: ToolOutput) -> None:
    if output.call.outcome == "timeout":
        ctx.failed_actions.append(action.id)


# --- company -----------------------------------------------------------------------------------


def _registry_call(ctx: SpecialistContext, action: Action, model: type, specialist: str) -> ToolOutput:
    arguments = targets.registry_arguments(action.tool, ctx.pack)
    if isinstance(arguments, targets.Skip):
        return ctx.runner.skip(specialist, action.tool, action.target, arguments.reason)
    expected = arguments.get("ruc") or arguments.get("expediente_or_ruc")
    output = ctx.runner.run(
        specialist=specialist, tool=action.tool, target=action.target, arguments=arguments,
        model=model, budget=ctx.budget, expect_ruc=expected,
    )  # fmt: skip
    _mark(ctx, action, output)
    return output


def company_info(ctx: SpecialistContext) -> None:
    action = Action("get_compania_info", "winner")
    output = _registry_call(ctx, action, CompaniaInfo, "company")
    if output.value is not None:
        ctx.findings["company"] = convert.company_facts(output.value, ctx.pack, ctx.today)
        _flag_out_of_range(output, ctx.findings["company"])
    else:
        ctx.findings["company"] = _status_facts(CompanyRegistryFacts, output)


def company_financials(ctx: SpecialistContext) -> None:
    action = Action("get_financials", "winner")
    output = _registry_call(ctx, action, Financials, "company")
    if output.value is not None:
        ctx.findings["financials"] = convert.financials_facts(output.value, ctx.pack, ctx.today)
        _flag_out_of_range(output, ctx.findings["financials"])
    else:
        ctx.findings["financials"] = _status_facts(CompanyFinancialsFacts, output)


# --- tax registry ------------------------------------------------------------------------------


def tax_live(ctx: SpecialistContext) -> None:
    action = Action("get_sri_ruc_info", "winner")
    output = _registry_call(ctx, action, SriRucInfo, "tax_registry")
    if output.value is not None:
        ctx.findings["tax_registry"] = convert.tax_facts(output.value, ctx.pack, ctx.today)
        _flag_out_of_range(output, ctx.findings["tax_registry"])
    else:
        ctx.findings["tax_registry"] = _status_facts(TaxRegistryLiveFacts, output)


# --- history -----------------------------------------------------------------------------------


def history_pair(ctx: SpecialistContext) -> None:
    action = Action("pair_awards", "winner")
    arguments = targets.pair_arguments(ctx.pack)
    if isinstance(arguments, targets.Skip):
        ctx.runner.skip("history", action.tool, action.target, arguments.reason)
        return
    output = ctx.runner.run(
        specialist="history", tool=action.tool, target=action.target, arguments=arguments,
        model=PairAwards, budget=ctx.budget,
    )  # fmt: skip
    _mark(ctx, action, output)
    if output.value is None:
        ctx.findings["pair_history"] = PairHistoryFacts(outcome=output.call.outcome)
        return
    v = output.value
    ctx.findings["pair_history"] = PairHistoryFacts(
        outcome="ok",
        n_other_awards=v.n_other_awards,
        n_with_amount=v.n_with_amount,
        total_other_amount=None if v.total_other_amount is None else round(v.total_other_amount, 2),
    )


def history_similar(ctx: SpecialistContext) -> None:
    action = Action("similar_processes", "process")
    arguments = targets.similar_arguments(ctx.pack)
    if isinstance(arguments, targets.Skip):
        ctx.runner.skip("history", action.tool, action.target, arguments.reason)
        return
    output = ctx.runner.run(
        specialist="history", tool=action.tool, target=action.target, arguments=arguments,
        model=SimilarSummary, budget=ctx.budget,
    )  # fmt: skip
    _mark(ctx, action, output)
    if output.value is None:
        ctx.findings["similar"] = SimilarPurchasesFacts(outcome=output.call.outcome)
        return
    v = output.value
    ctx.findings["similar"] = SimilarPurchasesFacts(
        outcome="ok",
        window_days=targets.SIMILAR_WINDOW_DAYS,
        neighbours_examined=v.neighbours_examined,
        similarity_floor=targets.SIMILARITY_FLOOR,
        n_above_floor=v.n_above_floor,
        basis=v.basis,
        n_in_window=v.n_in_window,
        n_with_amount=v.n_with_amount,
        combined_amount=None if v.combined_amount is None else round(v.combined_amount, 2),
    )


# --- audit -------------------------------------------------------------------------------------


def audit_catalogue(ctx: SpecialistContext) -> None:
    action = Action("list_catalogo", "buyer")
    name = targets.audit_buyer_name(ctx.pack)
    if isinstance(name, targets.Skip):
        ctx.runner.skip("audit", action.tool, action.target, name.reason)
        return
    output = ctx.runner.run(
        specialist="audit", tool=action.tool, target=action.target,
        arguments={"fuente": "contraloria", "format": "json"}, model=Catalogue, budget=ctx.budget,
    )  # fmt: skip
    _mark(ctx, action, output)
    if output.value is None:
        ctx.findings["audit"] = _status_facts(AuditFacts, output)
        return
    ids, total = convert.report_file_ids(output.value)
    if not ids:
        ctx.runner.skip("audit", "get_contraloria_informe", "buyer", "no_reports_in_catalogue")
        ctx.findings["audit"] = AuditFacts(outcome="skipped")
        return
    ctx.scratch["audit_file_ids"] = ids
    ctx.scratch["audit_catalogue_size"] = total


def audit_reports(ctx: SpecialistContext) -> None:
    action = Action("get_contraloria_informe", "buyer")
    ids: list[str] | None = ctx.scratch.get("audit_file_ids")
    if not ids:  # the catalogue step failed, was skipped or listed nothing usable
        return
    files: list[ReportsFile] = []
    last = None
    for file_id in ids:
        output = ctx.runner.run(
            specialist="audit", tool=action.tool, target=action.target,
            arguments={"informe_id": file_id, "rows": 200, "format": "json"},
            model=ReportsFile, budget=ctx.budget,
        )  # fmt: skip
        _mark(ctx, action, output)
        last = output
        if output.value is not None and convert.has_report_columns(output.value.headers):
            files.append(output.value)
    if not files:
        ctx.findings["audit"] = _status_facts(AuditFacts, last) if last is not None else AuditFacts()
        if last is not None and last.value is not None:  # parsed, but not the layout we know
            ctx.findings["audit"] = AuditFacts(outcome="invalid_result")
        return
    index = None
    if ctx.key_index is not None:
        try:
            index = ctx.key_index()
        except Exception:  # noqa: BLE001 - without the directory, matching is not reliable
            index = None
    name = targets.audit_buyer_name(ctx.pack)
    ctx.findings["audit"] = convert.audit_facts(
        name if isinstance(name, str) else None,
        files,
        files_in_catalogue=ctx.scratch.get("audit_catalogue_size", len(ids)),
        key_index=index,
        process_day=convert.reference_date(ctx.pack),
        today=ctx.today,
    )


# --- enquiries ---------------------------------------------------------------------------------


def enquiries_summary(ctx: SpecialistContext) -> None:
    """Counts and dates of the process's own questions and answers, computed by code from the stored
    texts. The tool returns numbers only: no text reaches the pack, the dossier or a model."""
    action = Action("process_texts", "process")
    arguments = targets.enquiry_arguments(ctx.pack)
    if isinstance(arguments, targets.Skip):
        ctx.runner.skip("enquiries", action.tool, action.target, arguments.reason)
        return
    output = ctx.runner.run(
        specialist="enquiries", tool=action.tool, target=action.target, arguments=arguments,
        model=EnquirySummary, budget=ctx.budget,
    )  # fmt: skip
    _mark(ctx, action, output)
    if output.value is None:
        ctx.findings["enquiries"] = EnquiriesFacts(outcome=output.call.outcome)
        return
    ctx.findings["enquiries"] = convert.enquiries_facts(output.value, ctx.pack, arguments)


@dataclass(frozen=True)
class SpecialistSpec:
    name: str
    handlers: dict[str, Handler]  # action id -> handler


SPECIALISTS: dict[str, SpecialistSpec] = {
    "company": SpecialistSpec(
        "company",
        {"get_compania_info:winner": company_info, "get_financials:winner": company_financials},
    ),
    "tax_registry": SpecialistSpec("tax_registry", {"get_sri_ruc_info:winner": tax_live}),
    "history": SpecialistSpec(
        "history",
        {"pair_awards:winner": history_pair, "similar_processes:process": history_similar},
    ),
    "audit": SpecialistSpec(
        "audit",
        {"list_catalogo:buyer": audit_catalogue, "get_contraloria_informe:buyer": audit_reports},
    ),
    "enquiries": SpecialistSpec("enquiries", {"process_texts:process": enquiries_summary}),
}
