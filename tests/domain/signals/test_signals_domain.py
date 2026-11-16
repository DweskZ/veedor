from __future__ import annotations

import pytest

from veedor.domain.signals import (
    CONTEXT_CODES,
    MAX_SCORE,
    RISK_CODES,
    SIGNAL_WEIGHTS,
    SIGNALS,
    SIGNALS_BY_CODE,
    get_signal,
    risk_score,
    supplier_kind,
)

CONTRACT_CODES = {
    "SINGLE_BIDDER", "SHORT_TENDER_WINDOW", "LOW_SAVING", "NEW_SUPPLIER", "SUPPLIER_NOT_ACTIVE",
    "GHOST_COMPANY_LIST", "BUYER_CONCENTRATION", "REPEATED_DIRECT_AWARDS", "RECURRING_COBIDDERS",
    "CONTRACT_VS_COMPANY_SIZE",
}  # fmt: skip
CONTEXT = {"GHOST_COMPANY_LISTED_LATER", "CONTRACT_VS_COMPANY_SIZE_SAME_YEAR"}


def test_registry_contains_the_contract_signals_plus_context_signals():
    assert {s.code for s in SIGNALS} == CONTRACT_CODES | CONTEXT
    assert {s.code for s in SIGNALS if s.is_context} == CONTEXT == set(CONTEXT_CODES)
    assert set(RISK_CODES) == CONTRACT_CODES
    assert len(SIGNALS) == len(SIGNALS_BY_CODE)


def test_every_signal_is_documented_and_weighted():
    for signal in SIGNALS:
        assert signal.label_es and signal.description_es and signal.scope and signal.threshold_rule_es
        assert signal.fields
        if signal.is_context:
            assert signal.code not in SIGNAL_WEIGHTS  # context signals weigh nothing
        else:
            assert SIGNAL_WEIGHTS[signal.code] > 0
    assert set(SIGNAL_WEIGHTS) == CONTRACT_CODES


def test_registry_dependent_signals_declare_their_tables():
    needing = {s.code for s in SIGNALS if s.needs_registry}
    assert (
        needing
        == {
            "NEW_SUPPLIER",
            "SUPPLIER_NOT_ACTIVE",
            "GHOST_COMPANY_LIST",
            "CONTRACT_VS_COMPANY_SIZE",
        }
        | CONTEXT
    )


def test_descriptions_avoid_accusatory_wording():
    banned = ("corrup", "fraude", "irregular", "culpable")
    for signal in SIGNALS:
        text = f"{signal.label_es} {signal.description_es}".lower()
        assert not any(word in text for word in banned), signal.code


def test_get_signal_unknown_code():
    assert get_signal("SINGLE_BIDDER").code == "SINGLE_BIDDER"
    with pytest.raises(KeyError):
        get_signal("NOPE")


def test_risk_score_sums_distinct_weights():
    assert risk_score([]) == 0.0
    assert risk_score(["SINGLE_BIDDER"]) == SIGNAL_WEIGHTS["SINGLE_BIDDER"]
    assert risk_score(["SINGLE_BIDDER", "SINGLE_BIDDER"]) == SIGNAL_WEIGHTS["SINGLE_BIDDER"]
    two = risk_score(["SINGLE_BIDDER", "LOW_SAVING"])
    assert two == SIGNAL_WEIGHTS["SINGLE_BIDDER"] + SIGNAL_WEIGHTS["LOW_SAVING"]


def test_risk_score_is_capped():
    assert sum(SIGNAL_WEIGHTS.values()) > MAX_SCORE
    assert risk_score(list(SIGNAL_WEIGHTS)) == MAX_SCORE == 100.0


def test_context_signals_never_change_the_score():
    assert risk_score(["GHOST_COMPANY_LISTED_LATER", "CONTRACT_VS_COMPANY_SIZE_SAME_YEAR"]) == 0.0
    assert risk_score(["SINGLE_BIDDER", "GHOST_COMPANY_LISTED_LATER"]) == SIGNAL_WEIGHTS["SINGLE_BIDDER"]


def test_risk_score_rejects_unknown_codes():
    with pytest.raises(KeyError):
        risk_score(["NOPE"])


@pytest.mark.parametrize(
    ("ruc", "kind"),
    [
        ("0102030405001", "natural_person"),
        ("1790000000001", "company"),
        ("1760001120001", "public_entity"),
        ("1770000000001", "other"),
        ("179", "unknown"),
        (None, "unknown"),
        ("17900000000AB", "unknown"),
    ],
)
def test_supplier_kind(ruc, kind):
    assert supplier_kind(ruc) == kind
