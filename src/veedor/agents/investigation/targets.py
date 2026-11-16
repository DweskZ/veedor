"""Resolve a target reference (`winner`, `buyer`, `process`) into tool arguments, from the pack only.

The arguments of every tool are built here by code from identifiers that passed a strict pattern. A
reference is the only thing a model can name; the identifier behind it never comes from a tool result
(the one exception, a Contraloría file id, is validated against the catalogue by the audit specialist).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from veedor.domain.dossier.models import EvidencePack
from veedor.domain.investigation.convert import reference_date
from veedor.domain.investigation.enquiry_topics import LATE_WINDOW_DAYS
from veedor.domain.investigation.policies import REGISTRY_KINDS, buyer_is_nameable
from veedor.domain.masking import NATURAL_PERSON, kind_from_ruc

_RUC = re.compile(r"^[0-9]{13}$")
_OCID = re.compile(r"^ocds-[a-z0-9]{6}-[A-Za-z0-9._\-]{1,120}$")
SIMILAR_K = 50
SIMILAR_WINDOW_DAYS = 180
# Lower quartile (0.745) of 1,175 same-buyer top-50 similarities measured on the 25 highest-risk processes
# (median 0.81, 5th percentile 0.57); the objects below it were visibly unrelated. A judgement call.
SIMILARITY_FLOOR = 0.75


@dataclass(frozen=True)
class Skip:
    reason: str  # closed vocabulary: vocab.Reason


def winner_ruc(pack: EvidencePack) -> str | Skip:
    """The winner's real RUC when, and only when, it belongs to a company or a public entity."""
    w = pack.winner
    if w is None or not w.ruc:
        return Skip("no_identifier")
    if w.kind == NATURAL_PERSON or kind_from_ruc(w.ruc) == NATURAL_PERSON or "*" in w.ruc:
        return Skip("natural_person")
    if w.kind not in REGISTRY_KINDS or not _RUC.match(w.ruc) or w.ruc[2] not in "69":
        return Skip("not_registry_eligible")
    return w.ruc


def registry_arguments(tool: str, pack: EvidencePack) -> dict[str, Any] | Skip:
    ruc = winner_ruc(pack)
    if isinstance(ruc, Skip):
        return ruc
    if tool == "get_compania_info":
        return {"ruc": ruc, "format": "json"}
    if tool == "get_financials":
        return {"expediente_or_ruc": ruc, "format": "json"}
    if tool == "get_sri_ruc_info":
        # The default also fetches the establishments page, which the SRI answered with HTTP 500.
        return {"ruc": ruc, "include_establecimientos": False, "format": "json"}
    return Skip("tool_not_allowed")


def pair_arguments(pack: EvidencePack) -> dict[str, Any] | Skip:
    ruc = winner_ruc(pack)
    if isinstance(ruc, Skip):
        return ruc
    buyer = pack.process.buyer_ruc
    if not buyer or "*" in buyer or not _RUC.match(buyer):
        return Skip("no_identifier")
    return {"buyer_ruc": buyer, "supplier_ruc": ruc, "ocid": pack.process.ocid}


def similar_arguments(pack: EvidencePack) -> dict[str, Any] | Skip:
    ocid = pack.process.ocid
    reference = reference_date(pack)
    if not _OCID.match(ocid) or reference is None:
        return Skip("no_identifier")
    return {
        "ocid": ocid,
        "reference_day": reference.isoformat(),
        "window_days": SIMILAR_WINDOW_DAYS,
        "k": SIMILAR_K,
        "similarity_floor": SIMILARITY_FLOOR,
    }


def audit_buyer_name(pack: EvidencePack) -> str | Skip:
    if not buyer_is_nameable(pack):
        return Skip("no_buyer_name")
    return pack.process.buyer_name or ""


def enquiry_arguments(pack: EvidencePack) -> dict[str, Any] | Skip:
    """Arguments of `process_texts`: the process id, the offer deadline (a day) when published, the window."""
    ocid = pack.process.ocid
    if not _OCID.match(ocid):
        return Skip("no_identifier")
    deadline = pack.process.tender_end
    return {
        "ocid": ocid,
        "deadline_day": deadline[:10] if isinstance(deadline, str) and len(deadline) >= 10 else None,
        "late_days": LATE_WINDOW_DAYS,
    }
