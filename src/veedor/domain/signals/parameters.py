"""Numeric parameters of Signals v1, in one place.

Statistical thresholds (percentiles) are *not* here: they are computed from the data per
method-year. Only the percentile levels and the fixed rule constants live in this module.
"""

from __future__ import annotations

# --- Scope ---------------------------------------------------------------------------------
COMPETITIVE_GROUP = "competitive"
DIRECT_GROUP = "direct"
CATALOGUE_GROUP = "catalogue"

# A method-year needs at least this many processes before a percentile is trusted.
MIN_GROUP_SIZE = 30

# --- SINGLE_BIDDER -------------------------------------------------------------------------
SINGLE_BIDDER_TENDERERS = 1
# A method-category cell where at least this share of processes has one tenderer (and with at least
# MIN_GROUP_SIZE processes) is treated as "no competition recorded by design" and left out. Judgement
# call: in the real lake the excluded cells sit at 99.95 % and 100 %; every other cell is below 52 %.
SINGLE_BIDDER_BY_DESIGN_SHARE = 0.999

# --- SHORT_TENDER_WINDOW -------------------------------------------------------------------
SHORT_WINDOW_PERCENTILE = 0.05

# --- LOW_SAVING ----------------------------------------------------------------------------
LOW_SAVING_PERCENTILE = 0.95
LOW_SAVING_MIN_RATIO = 0.99
# If more than this share of a method-year sits at or above the threshold, the percentile is a
# mass point (e.g. awards equal to the budget by design) and being there is not atypical.
LOW_SAVING_MAX_SHARE = 0.10

# --- NEW_SUPPLIER --------------------------------------------------------------------------
NEW_SUPPLIER_MAX_DAYS = 180

# --- SUPPLIER_NOT_ACTIVE -------------------------------------------------------------------
ACTIVE_STATUSES = frozenset({"ACTIVO"})

# --- BUYER_CONCENTRATION -------------------------------------------------------------------
BUYER_CONCENTRATION_MIN_SHARE = 0.30
BUYER_CONCENTRATION_MIN_TOTAL = 100_000.0
BUYER_CONCENTRATION_MIN_AWARDS = 3

# --- REPEATED_DIRECT_AWARDS ----------------------------------------------------------------
REPEATED_DIRECT_MIN_PROCESSES = 3
REPEATED_DIRECT_WINDOW_DAYS = 90
REPEATED_DIRECT_CPC_PREFIX = 5

# --- RECURRING_COBIDDERS -------------------------------------------------------------------
RECURRING_COBIDDERS_MIN_MEETINGS = 5

# --- CONTRACT_VS_COMPANY_SIZE --------------------------------------------------------------
CONTRACT_SIZE_FACTOR = 3.0
# Reporting only (not a rule): firings resting on revenue below this are counted in the summary.
SMALL_REVENUE_USD = 1000.0

# --- Anomaly score -------------------------------------------------------------------------
ANOMALY_RANDOM_STATE = 42
ANOMALY_N_ESTIMATORS = 200
ANOMALY_MIN_ROWS = 500
ANOMALY_MIN_FEATURE_COVERAGE = 0.9
