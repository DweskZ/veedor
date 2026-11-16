"""Supervisor and specialist policies: budgets, the deterministic dispatch table, action menus (pure).

The supervisor and the specialists choose from the enumerations below; a model, when one is
configured, picks from the same enumerations and its choice is validated against them. Nothing a
tool returns can add an entry to any of these sets.
"""

from __future__ import annotations

from dataclasses import dataclass

from veedor.domain.dossier.models import EvidencePack
from veedor.domain.dossier.signal_text import is_informational
from veedor.domain.investigation.vocab import SPECIALISTS, DispatchReason, SpecialistName, TargetRef
from veedor.domain.masking import COMPANY, PUBLIC_ENTITY, kind_from_ruc

MAX_DISPATCHES = 6
MAX_DISPATCHES_PER_SPECIALIST = 2
MAX_TOOL_CALLS_PER_SPECIALIST = 4
REGISTRY_KINDS = frozenset({"company", "public_entity"})  # RUC third digit 9 or 6

# Which signals call for which specialist, in priority order, with the reason code recorded.
SIGNAL_TABLE: tuple[tuple[str, SpecialistName, DispatchReason], ...] = (
    ("NEW_SUPPLIER", "company", "new_supplier_signal"),
    ("NEW_SUPPLIER", "tax_registry", "new_supplier_signal"),
    ("SUPPLIER_NOT_ACTIVE", "tax_registry", "supplier_not_active_signal"),
    ("SUPPLIER_NOT_ACTIVE", "company", "supplier_not_active_signal"),
    ("GHOST_COMPANY_LIST", "tax_registry", "ghost_listing_signal"),
    ("CONTRACT_VS_COMPANY_SIZE", "company", "company_size_signal"),
    ("BUYER_CONCENTRATION", "history", "buyer_concentration_signal"),
    ("BUYER_CONCENTRATION", "audit", "buyer_concentration_signal"),
    ("REPEATED_DIRECT_AWARDS", "history", "repeated_awards_signal"),
    ("RECURRING_COBIDDERS", "history", "recurring_cobidders_signal"),
    ("SINGLE_BIDDER", "history", "single_bidder_signal"),
    ("SHORT_TENDER_WINDOW", "audit", "tender_window_signal"),
    ("LOW_SAVING", "history", "low_saving_signal"),
    ("SHORT_TENDER_WINDOW", "enquiries", "tender_window_signal"),
    ("SINGLE_BIDDER", "enquiries", "single_bidder_signal"),
    ("RECURRING_COBIDDERS", "enquiries", "recurring_cobidders_signal"),
)
BASELINE_ORDER: tuple[SpecialistName, ...] = ("company", "history", "audit", "tax_registry", "enquiries")


def winner_is_registry_eligible(pack: EvidencePack) -> bool:
    w = pack.winner
    return w is not None and w.kind in REGISTRY_KINDS and bool(w.ruc) and "*" not in (w.ruc or "")


def buyer_is_nameable(pack: EvidencePack) -> bool:
    """A buyer whose name may be compared with external records: an identified public entity."""
    ruc, name = pack.process.buyer_ruc, pack.process.buyer_name
    if not ruc or not name or "*" in ruc:
        return False
    return kind_from_ruc(ruc) in (PUBLIC_ENTITY, COMPANY)


def applicable_specialists(pack: EvidencePack) -> list[SpecialistName]:
    """Specialists that have something they may legitimately do for this pack."""
    out: list[SpecialistName] = []
    for name in SPECIALISTS:
        if name in ("company", "tax_registry") and not winner_is_registry_eligible(pack):
            continue
        if name == "audit" and not buyer_is_nameable(pack):
            continue
        if name == "enquiries" and not (pack.process.n_enquiries or 0) > 0:
            continue  # the process registered no question: there is nothing to describe
        out.append(name)
    return out


@dataclass(frozen=True)
class Dispatch:
    specialist: SpecialistName
    reason: DispatchReason


def default_plan(pack: EvidencePack, ran: dict[str, int] | None = None) -> list[Dispatch]:
    """The deterministic dispatch plan: signal-driven specialists first, then the baseline order.

    `ran` maps specialist -> dispatches so far; budgets are enforced by `check_dispatch`, this only
    avoids proposing a specialist that has already run.
    """
    ran = ran or {}
    eligible = set(applicable_specialists(pack))
    fired = {s.code for s in pack.signals if not is_informational(s)}
    plan: list[Dispatch] = []
    seen: set[str] = set(ran)
    for code, specialist, reason in SIGNAL_TABLE:
        if code in fired and specialist in eligible and specialist not in seen:
            plan.append(Dispatch(specialist, reason))
            seen.add(specialist)
    for specialist in BASELINE_ORDER:
        if specialist in eligible and specialist not in seen:
            plan.append(Dispatch(specialist, "baseline_check"))
            seen.add(specialist)
    return plan


class DispatchRejected(ValueError):
    """A proposed dispatch breaks a budget or names something outside the enumerations."""


def check_dispatch(
    specialist: str, reason: str, pack: EvidencePack, dispatches: list[str]
) -> tuple[SpecialistName, DispatchReason]:
    """Validate one proposed (specialist, reason) pair against the enumerations and the budgets."""
    from veedor.domain.investigation.vocab import DISPATCH_REASONS

    if specialist not in SPECIALISTS:
        raise DispatchRejected("unknown specialist")
    if reason not in DISPATCH_REASONS:
        raise DispatchRejected("unknown reason")
    if len(dispatches) >= MAX_DISPATCHES:
        raise DispatchRejected("dispatch budget exhausted")
    if dispatches.count(specialist) >= MAX_DISPATCHES_PER_SPECIALIST:
        raise DispatchRejected("specialist already dispatched twice")
    if specialist not in applicable_specialists(pack):
        raise DispatchRejected("specialist not applicable to this pack")
    return specialist, reason  # type: ignore[return-value]


@dataclass(frozen=True)
class Action:
    """One enumerated step: a tool and a reference into the pack. Never a free string."""

    tool: str
    target: TargetRef

    @property
    def id(self) -> str:
        return f"{self.tool}:{self.target}"


ACTION_MENU: dict[SpecialistName, tuple[Action, ...]] = {
    "company": (Action("get_compania_info", "winner"), Action("get_financials", "winner")),
    "tax_registry": (Action("get_sri_ruc_info", "winner"),),
    "history": (Action("pair_awards", "winner"), Action("similar_processes", "process")),
    "audit": (Action("list_catalogo", "buyer"), Action("get_contraloria_informe", "buyer")),
    "enquiries": (Action("process_texts", "process"),),
}
# The default sequence is the menu in order; a model may only reorder or drop entries.
ALLOWED_TOOLS: dict[SpecialistName, frozenset[str]] = {
    name: frozenset(a.tool for a in actions) for name, actions in ACTION_MENU.items()
}
# Contraloría: the catalogue call plus at most this many report files, so the 4-call budget holds.
MAX_REPORT_FILES = MAX_TOOL_CALLS_PER_SPECIALIST - 1


def check_actions(specialist: str, action_ids: list[str]) -> list[Action]:
    """Validate a model-proposed action order: members of the menu, no repeats, within budget."""
    menu = {a.id: a for a in ACTION_MENU[specialist]}  # type: ignore[index]
    if len(action_ids) > MAX_TOOL_CALLS_PER_SPECIALIST:
        raise DispatchRejected("too many actions")
    if len(set(action_ids)) != len(action_ids):
        raise DispatchRejected("repeated action")
    chosen = []
    for action_id in action_ids:
        if action_id not in menu:
            raise DispatchRejected("action not in the menu")
        chosen.append(menu[action_id])
    return chosen
