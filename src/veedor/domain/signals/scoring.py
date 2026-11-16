"""Risk score: weighted sum of fired signals, capped at 100.

The weights below are judgement calls, not calibrated against labelled outcomes. They only
express a relative ordering: signals that rest on a registry fact or on repeated behaviour weigh
more than signals that are common and often benign.
"""

from __future__ import annotations

from collections.abc import Iterable

from veedor.domain.signals import definitions as d

MAX_SCORE = 100.0

SIGNAL_WEIGHTS: dict[str, float] = {
    d.SINGLE_BIDDER: 20.0,
    d.SHORT_TENDER_WINDOW: 10.0,
    d.LOW_SAVING: 10.0,
    d.NEW_SUPPLIER: 15.0,
    d.SUPPLIER_NOT_ACTIVE: 15.0,
    d.GHOST_COMPANY_LIST: 30.0,
    d.BUYER_CONCENTRATION: 15.0,
    d.REPEATED_DIRECT_AWARDS: 15.0,
    d.RECURRING_COBIDDERS: 15.0,
    d.CONTRACT_VS_COMPANY_SIZE: 15.0,
}


def risk_score(codes: Iterable[str]) -> float:
    """Sum the weights of the distinct fired risk signals and cap at MAX_SCORE.

    Context signals are informational and weigh nothing; unknown codes raise KeyError.
    """
    total = sum(SIGNAL_WEIGHTS[code] for code in set(codes) if code not in d.CONTEXT_CODES)
    return min(total, MAX_SCORE)
