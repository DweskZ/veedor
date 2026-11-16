"""DuckDB SQL for Signals v1. One clearly named statement per signal.

Every statement reads the temp tables prepared by `PREPARE_STATEMENTS` and appends rows to
`signal_rows`. Parameters are bound (`$name`); only identifiers are ever interpolated.

Temp tables
-----------
base         one row per process, typed (dates parsed, year, method_group, award figures)
winners      one row per process with an award: the supplier with the largest amount
thresholds   per signal, method and year: percentile, threshold, share flagged, status
signal_rows  fired signals: ocid, signal_code, value, threshold, evidence_json
"""

from __future__ import annotations

# Registry-derived signals are computed only for winners that are companies (RUC third digit 9) or
# public entities (6). Natural persons and winners without a valid RUC never get registry facts
# (listing, tax status, activity start): Veedor does not publish registry information about
# individuals. Mirrors `domain.signals.kinds.supplier_kind`.
REGISTRY_ELIGIBLE = "(length(w.supplier_ruc) = 13 AND substr(w.supplier_ruc, 3, 1) IN ('9', '6'))"

# --- Preparation ---------------------------------------------------------------------------

CREATE_BASE = """
CREATE OR REPLACE TEMP TABLE base AS
SELECT
    ocid, year, method, method_group, category, buyer_ruc, buyer_name, budget, award_total,
    n_tenderers, n_enquiries, main_cpc, tender_start, tender_end, first_award_date,
    date_signed, release_date,
    TRY_CAST(tender_start AS TIMESTAMPTZ) AS t_start,
    TRY_CAST(tender_end AS TIMESTAMPTZ) AS t_end,
    TRY_CAST(substr(first_award_date, 1, 10) AS DATE) AS first_award_day,
    -- Process date: first award, else signature, else tender start, else release date.
    coalesce(
        TRY_CAST(substr(first_award_date, 1, 10) AS DATE),
        TRY_CAST(substr(date_signed, 1, 10) AS DATE),
        TRY_CAST(substr(tender_start, 1, 10) AS DATE),
        TRY_CAST(substr(release_date, 1, 10) AS DATE)
    ) AS process_day
FROM processes
"""

# Winner = the supplier with a RUC and the largest amount; amounts are null when an award lists
# several suppliers, in which case the smallest RUC breaks the tie so the choice is deterministic.
CREATE_WINNERS = """
CREATE OR REPLACE TEMP TABLE winners AS
SELECT ocid, supplier_id, supplier_ruc, supplier_name, amount
FROM awards
WHERE supplier_id IS NOT NULL OR supplier_ruc IS NOT NULL
QUALIFY row_number() OVER (
    PARTITION BY ocid
    ORDER BY (supplier_ruc IS NULL), amount DESC NULLS LAST, supplier_ruc, supplier_id
) = 1
"""

CREATE_THRESHOLDS = """
CREATE OR REPLACE TEMP TABLE thresholds (
    signal_code VARCHAR, method VARCHAR, year INTEGER, n BIGINT,
    percentile_value DOUBLE, threshold DOUBLE, share_flagged DOUBLE, status VARCHAR
)
"""

CREATE_SIGNAL_ROWS = """
CREATE OR REPLACE TEMP TABLE signal_rows (
    ocid VARCHAR, signal_code VARCHAR, value DOUBLE, threshold DOUBLE, evidence_json VARCHAR
)
"""

CREATE_WEIGHTS = "CREATE OR REPLACE TEMP TABLE weights (signal_code VARCHAR, weight DOUBLE)"

# --- SINGLE_BIDDER -------------------------------------------------------------------------

# Method-category cells where practically every process (>= by_design_share) has exactly one
# tenderer, with enough processes, record no competition by design (Menor Cuantia for goods and
# services in the real lake): one bidder there carries no information, so they are excluded.
# Derived from the data, not hard-coded.
SINGLE_BIDDER_EXEMPT = """
CREATE OR REPLACE TEMP TABLE single_bidder_exempt AS
SELECT method, category, count(*) AS n
FROM base
WHERE method_group = $competitive AND n_tenderers IS NOT NULL AND method IS NOT NULL
GROUP BY method, category
HAVING count(*) >= $min_group AND avg((n_tenderers = $max_tenderers)::DOUBLE) >= $by_design_share
"""

SINGLE_BIDDER = """
INSERT INTO signal_rows
SELECT b.ocid, 'SINGLE_BIDDER', b.n_tenderers, $max_tenderers,
       json_object('method', b.method, 'year', b.year, 'n_tenderers', b.n_tenderers)::VARCHAR
FROM base b
WHERE b.method_group = $competitive AND b.n_tenderers = $max_tenderers
  AND NOT EXISTS (
      SELECT 1 FROM single_bidder_exempt e
      WHERE e.method = b.method AND e.category IS NOT DISTINCT FROM b.category
  )
"""

# --- SHORT_TENDER_WINDOW -------------------------------------------------------------------

SHORT_WINDOW_TABLE = """
CREATE OR REPLACE TEMP TABLE windows AS
SELECT ocid, method, year, tender_start, tender_end,
       (epoch(t_end) - epoch(t_start)) / 86400.0 AS days
FROM base
WHERE method_group = $competitive AND t_start IS NOT NULL AND t_end IS NOT NULL
  AND t_end > t_start AND year IS NOT NULL AND method IS NOT NULL
"""

SHORT_WINDOW_THRESHOLDS = """
INSERT INTO thresholds
WITH g AS (
    SELECT method, year, count(*) AS n, quantile_cont(days, $percentile) AS pv
    FROM windows GROUP BY method, year
),
s AS (
    SELECT g.method, g.year, avg((w.days < g.pv)::DOUBLE) AS share
    FROM windows w JOIN g USING (method, year) GROUP BY g.method, g.year
)
SELECT 'SHORT_TENDER_WINDOW', g.method, g.year, g.n, g.pv, g.pv, s.share,
       CASE WHEN g.n < $min_group THEN 'skipped_small_group' ELSE 'used' END
FROM g JOIN s USING (method, year)
"""

SHORT_TENDER_WINDOW = """
INSERT INTO signal_rows
SELECT w.ocid, 'SHORT_TENDER_WINDOW', w.days, t.threshold,
       json_object(
           'method', w.method, 'year', w.year,
           'tender_start', w.tender_start, 'tender_end', w.tender_end,
           'window_days', round(w.days, 2), 'p05_days', round(t.threshold, 2),
           'n_method_year', t.n
       )::VARCHAR
FROM windows w
JOIN thresholds t ON t.signal_code = 'SHORT_TENDER_WINDOW' AND t.method = w.method
                 AND t.year = w.year AND t.status = 'used'
WHERE w.days < t.threshold
"""

# --- LOW_SAVING ----------------------------------------------------------------------------

LOW_SAVING_TABLE = """
CREATE OR REPLACE TEMP TABLE ratios AS
SELECT ocid, method, year, budget, award_total, award_total / budget AS ratio
FROM base
WHERE method_group = $competitive AND budget > 0 AND award_total > 0
  AND year IS NOT NULL AND method IS NOT NULL
"""

LOW_SAVING_THRESHOLDS = """
INSERT INTO thresholds
WITH g AS (
    SELECT method, year, count(*) AS n, quantile_cont(ratio, $percentile) AS pv,
           greatest(quantile_cont(ratio, $percentile), $min_ratio) AS thr
    FROM ratios GROUP BY method, year
),
s AS (
    SELECT g.method, g.year, avg((r.ratio >= g.thr)::DOUBLE) AS share
    FROM ratios r JOIN g USING (method, year) GROUP BY g.method, g.year
)
SELECT 'LOW_SAVING', g.method, g.year, g.n, g.pv, g.thr, s.share,
       CASE WHEN g.n < $min_group THEN 'skipped_small_group'
            WHEN s.share > $max_share THEN 'skipped_mass_point'
            ELSE 'used' END
FROM g JOIN s USING (method, year)
"""

LOW_SAVING = """
INSERT INTO signal_rows
SELECT r.ocid, 'LOW_SAVING', r.ratio, t.threshold,
       json_object(
           'method', r.method, 'year', r.year, 'budget', r.budget, 'award_total', r.award_total,
           'award_to_budget', round(r.ratio, 4), 'p95_ratio', round(t.percentile_value, 4),
           'threshold', round(t.threshold, 4), 'n_method_year', t.n
       )::VARCHAR
FROM ratios r
JOIN thresholds t ON t.signal_code = 'LOW_SAVING' AND t.method = r.method
                 AND t.year = r.year AND t.status = 'used'
WHERE r.ratio >= t.threshold
"""

# --- BUYER_CONCENTRATION -------------------------------------------------------------------

# Concentration must be accumulated: no single process of the supplier may reach the share
# threshold by itself (otherwise one large contract, not a pattern, drives the share).
BUYER_CONCENTRATION = """
INSERT INTO signal_rows
WITH amounts AS (
    SELECT a.ocid, a.supplier_ruc, a.supplier_name, a.amount, b.buyer_ruc, b.year
    FROM awards a JOIN base b USING (ocid)
    WHERE b.method_group <> $catalogue AND b.buyer_ruc IS NOT NULL AND b.year IS NOT NULL
      AND a.amount > 0
),
buyer_year AS (
    SELECT buyer_ruc, year, sum(amount) AS total, count(DISTINCT ocid) AS n_awards
    FROM amounts GROUP BY buyer_ruc, year
),
supplier_process AS (
    SELECT buyer_ruc, year, supplier_ruc, ocid, sum(amount) AS process_amount
    FROM amounts WHERE supplier_ruc IS NOT NULL GROUP BY buyer_ruc, year, supplier_ruc, ocid
),
supplier_year AS (
    SELECT buyer_ruc, year, supplier_ruc, sum(process_amount) AS supplier_amount,
           max(process_amount) AS largest_process_amount, count(*) AS supplier_awards
    FROM supplier_process GROUP BY buyer_ruc, year, supplier_ruc
),
concentrated AS (
    SELECT s.buyer_ruc, s.year, s.supplier_ruc, s.supplier_amount, s.largest_process_amount,
           s.supplier_awards, y.total, y.n_awards, s.supplier_amount / y.total AS share
    FROM supplier_year s JOIN buyer_year y USING (buyer_ruc, year)
    WHERE y.total >= $min_total AND y.n_awards >= $min_awards
      AND s.supplier_amount / y.total >= $min_share
      AND s.largest_process_amount / y.total < $min_share
)
SELECT DISTINCT ON (a.ocid)
       a.ocid, 'BUYER_CONCENTRATION', c.share, $min_share,
       json_object(
           'year', c.year, 'buyer_ruc', c.buyer_ruc, 'supplier_ruc', c.supplier_ruc,
           'supplier_name', a.supplier_name,
           'supplier_amount', round(c.supplier_amount, 2), 'buyer_total', round(c.total, 2),
           'share', round(c.share, 4), 'n_awards_buyer_year', c.n_awards,
           'supplier_awards', c.supplier_awards,
           'largest_supplier_process_share', round(c.largest_process_amount / c.total, 4)
       )::VARCHAR
FROM amounts a
JOIN concentrated c ON c.buyer_ruc = a.buyer_ruc AND c.year = a.year
                   AND c.supplier_ruc = a.supplier_ruc
ORDER BY a.ocid, c.share DESC, c.supplier_ruc
"""

# --- REPEATED_DIRECT_AWARDS ----------------------------------------------------------------
# For each direct process, look for a window [anchor, anchor + N days] that contains it and holds
# at least `min_processes` processes of the same buyer, supplier and CPC prefix.

REPEATED_DIRECT_AWARDS = """
INSERT INTO signal_rows
WITH direct AS (
    SELECT b.ocid, b.buyer_ruc, w.supplier_ruc, left(b.main_cpc, $cpc_prefix) AS cpc_prefix,
           date_diff('day', DATE '1970-01-01',
                     coalesce(b.first_award_day, TRY_CAST(substr(b.tender_start, 1, 10) AS DATE))) AS day_n
    FROM base b JOIN winners w USING (ocid)
    WHERE b.method_group = $direct AND b.buyer_ruc IS NOT NULL AND w.supplier_ruc IS NOT NULL
      AND length(b.main_cpc) >= $cpc_prefix
),
forward AS (
    SELECT *, count(*) OVER (
        PARTITION BY buyer_ruc, supplier_ruc, cpc_prefix ORDER BY day_n
        RANGE BETWEEN CURRENT ROW AND __WINDOW_DAYS__ FOLLOWING
    ) AS n_forward
    FROM direct WHERE day_n IS NOT NULL
),
best AS (
    SELECT *,
        max(n_forward) OVER (
            PARTITION BY buyer_ruc, supplier_ruc, cpc_prefix ORDER BY day_n
            RANGE BETWEEN __WINDOW_DAYS__ PRECEDING AND CURRENT ROW
        ) AS n_best,
        arg_max(day_n, n_forward) OVER (
            PARTITION BY buyer_ruc, supplier_ruc, cpc_prefix ORDER BY day_n
            RANGE BETWEEN __WINDOW_DAYS__ PRECEDING AND CURRENT ROW
        ) AS anchor_n,
        count(*) OVER (PARTITION BY buyer_ruc, supplier_ruc, cpc_prefix) AS n_group
    FROM forward
)
SELECT ocid, 'REPEATED_DIRECT_AWARDS', n_best, $min_processes,
       json_object(
           'buyer_ruc', buyer_ruc, 'supplier_ruc', supplier_ruc, 'cpc_prefix', cpc_prefix,
           'n_in_window', n_best, 'window_days', $window_days,
           'window_start', DATE '1970-01-01' + anchor_n::INTEGER,
           'window_end', DATE '1970-01-01' + (anchor_n + $window_days)::INTEGER,
           'n_same_buyer_supplier_cpc', n_group
       )::VARCHAR
FROM best
WHERE n_best >= $min_processes
"""

# --- RECURRING_COBIDDERS -------------------------------------------------------------------

RECURRING_COBIDDERS = """
INSERT INTO signal_rows
WITH matches AS (
    SELECT b.ocid, b.buyer_ruc, w.supplier_ruc AS winner_ruc, w.supplier_name AS winner_name,
           t.supplier_ruc AS loser_ruc, t.supplier_name AS loser_name
    FROM base b
    JOIN winners w USING (ocid)
    JOIN tenderers t USING (ocid)
    WHERE b.method_group = $competitive AND b.buyer_ruc IS NOT NULL
      AND w.supplier_ruc IS NOT NULL AND t.supplier_ruc IS NOT NULL
      AND t.supplier_ruc <> w.supplier_ruc
),
pairs AS (
    SELECT buyer_ruc, winner_ruc, loser_ruc, count(DISTINCT ocid) AS n_meetings
    FROM matches GROUP BY buyer_ruc, winner_ruc, loser_ruc
    HAVING count(DISTINCT ocid) >= $min_meetings
),
per_process AS (
    SELECT m.ocid, m.buyer_ruc, m.winner_ruc, m.winner_name,
           count(*) AS n_recurring_losers,
           arg_max(m.loser_ruc, p.n_meetings) AS top_loser_ruc,
           arg_max(m.loser_name, p.n_meetings) AS top_loser_name,
           max(p.n_meetings) AS top_meetings
    FROM matches m
    JOIN pairs p USING (buyer_ruc, winner_ruc, loser_ruc)
    GROUP BY m.ocid, m.buyer_ruc, m.winner_ruc, m.winner_name
)
SELECT ocid, 'RECURRING_COBIDDERS', top_meetings, $min_meetings,
       json_object(
           'buyer_ruc', buyer_ruc, 'winner_ruc', winner_ruc, 'winner_name', winner_name,
           'cobidder_ruc', top_loser_ruc, 'cobidder_name', top_loser_name,
           'n_meetings', top_meetings, 'n_recurring_cobidders_in_process', n_recurring_losers
       )::VARCHAR
FROM per_process
"""

# --- Registry-dependent signals ------------------------------------------------------------
# `sri` (one row per RUC: ruc, status, activity_start, suspension_date, restart_date),
# `ghosts` (ruc, ...) and `financials` (ruc, year, revenue) are temp tables created by the
# builder from the Parquet tables, only when those tables exist.

NEW_SUPPLIER = """
INSERT INTO signal_rows
SELECT b.ocid, 'NEW_SUPPLIER', date_diff('day', s.activity_start, b.first_award_day), $max_days,
       json_object(
           'supplier_ruc', w.supplier_ruc, 'supplier_name', w.supplier_name,
           'activity_start_date', s.activity_start, 'first_award_date', b.first_award_day,
           'days_between', date_diff('day', s.activity_start, b.first_award_day)
       )::VARCHAR
FROM base b
JOIN winners w USING (ocid)
JOIN sri s ON s.ruc = w.supplier_ruc
WHERE b.method_group <> $catalogue AND __REGISTRY_ELIGIBLE__ AND b.first_award_day IS NOT NULL
  AND s.activity_start >= DATE '1900-01-01' AND s.activity_start <= b.first_award_day
  AND date_diff('day', s.activity_start, b.first_award_day) < $max_days
"""

# Fires when the current status is not active and the data does not show the supplier was still
# active at the process date: a suspension_date after the process date means "do not fire".
# Without a (parseable) suspension_date the timing cannot be established ("timing": "unknown").
# restart_date is not used: in the registry it precedes suspension_date for ~99 % of rows.
SUPPLIER_NOT_ACTIVE = """
INSERT INTO signal_rows
WITH matched AS (
    SELECT b.ocid, b.process_day, w.supplier_ruc, w.supplier_name, s.status, s.restart_date,
           s.suspension_date,
           TRY_CAST(substr(s.suspension_date, 1, 10) AS DATE) AS suspension_day
    FROM base b
    JOIN winners w USING (ocid)
    JOIN sri s ON s.ruc = w.supplier_ruc
    WHERE b.method_group <> $catalogue AND __REGISTRY_ELIGIBLE__ AND s.status IS NOT NULL
      AND upper(trim(s.status)) NOT IN (SELECT unnest($active_statuses))
)
SELECT ocid, 'SUPPLIER_NOT_ACTIVE', 1.0, 1.0,
       json_object(
           'supplier_ruc', supplier_ruc, 'supplier_name', supplier_name,
           'sri_status', status, 'status_is_current', true,
           'suspension_date', suspension_date, 'restart_date', restart_date,
           'process_date', process_day,
           'timing', CASE WHEN suspension_day IS NULL OR process_day IS NULL
                          THEN 'unknown' ELSE 'suspended_before_process' END
       )::VARCHAR
FROM matched
WHERE suspension_day IS NULL OR process_day IS NULL OR suspension_day <= process_day
"""

# The SRI listing counts as a risk signal only when its notification date is on or before the
# process date; later (or undated) listings are context, because the buyer could not have known.
GHOST_COMPANY_LIST = """
INSERT INTO signal_rows
SELECT b.ocid, 'GHOST_COMPANY_LIST', 1.0, 1.0,
       json_object(
           'supplier_ruc', w.supplier_ruc, 'supplier_name', w.supplier_name,
           'resolution', g.resolution, 'notification_date', g.notification_date,
           'qualification_detail', g.qualification_detail, 'challenge_state', g.challenge_state,
           'process_date', b.process_day, 'listed_after_process', false
       )::VARCHAR
FROM base b
JOIN winners w USING (ocid)
JOIN ghosts g ON g.ruc = w.supplier_ruc
WHERE __REGISTRY_ELIGIBLE__ AND g.notification_day <= b.process_day
"""

GHOST_COMPANY_LISTED_LATER = """
INSERT INTO signal_rows
SELECT b.ocid, 'GHOST_COMPANY_LISTED_LATER', 1.0, 1.0,
       json_object(
           'supplier_ruc', w.supplier_ruc, 'supplier_name', w.supplier_name,
           'resolution', g.resolution, 'notification_date', g.notification_date,
           'qualification_detail', g.qualification_detail, 'challenge_state', g.challenge_state,
           'process_date', b.process_day,
           'timing', CASE WHEN g.notification_day IS NULL THEN 'notification_date_missing'
                          ELSE 'listed_after_process' END
       )::VARCHAR
FROM base b
JOIN winners w USING (ocid)
JOIN ghosts g ON g.ruc = w.supplier_ruc
WHERE __REGISTRY_ELIGIBLE__ AND (g.notification_day IS NULL OR g.notification_day > b.process_day)
"""

# Comparison revenue: the latest year strictly before the award year; only when none exists, the
# award year itself (which may include the contract, hence context only).
SIZE_PICK = """
CREATE OR REPLACE TEMP TABLE size_pick AS
SELECT ocid, award_total, supplier_ruc, supplier_name, year, revenue, award_year FROM (
    SELECT b.ocid, b.award_total, w.supplier_ruc, w.supplier_name, f.year, f.revenue,
           coalesce(year(b.first_award_day), b.year) AS award_year
    FROM base b
    JOIN winners w USING (ocid)
    JOIN financials f ON f.ruc = w.supplier_ruc
    WHERE b.method_group <> $catalogue AND b.award_total > 0 AND __REGISTRY_ELIGIBLE__
      AND f.year <= coalesce(year(b.first_award_day), b.year)
    QUALIFY row_number() OVER (
        PARTITION BY b.ocid
        ORDER BY (f.year = coalesce(year(b.first_award_day), b.year)), f.year DESC
    ) = 1
)
WHERE award_total > $factor * revenue
"""

CONTRACT_VS_COMPANY_SIZE = """
INSERT INTO signal_rows
SELECT ocid, 'CONTRACT_VS_COMPANY_SIZE', award_total / revenue, $factor,
       json_object(
           'supplier_ruc', supplier_ruc, 'supplier_name', supplier_name,
           'award_total', award_total, 'revenue', revenue, 'revenue_year', year,
           'award_year', award_year, 'years_before_award', award_year - year,
           'comparison', 'prior_year',
           'ratio', round(award_total / revenue, 2), 'factor', $factor
       )::VARCHAR
FROM size_pick
WHERE year < award_year
"""

CONTRACT_VS_COMPANY_SIZE_SAME_YEAR = """
INSERT INTO signal_rows
SELECT ocid, 'CONTRACT_VS_COMPANY_SIZE_SAME_YEAR', award_total / revenue, $factor,
       json_object(
           'supplier_ruc', supplier_ruc, 'supplier_name', supplier_name,
           'award_total', award_total, 'revenue', revenue, 'revenue_year', year,
           'award_year', award_year, 'comparison', 'same_year',
           'ratio', round(award_total / revenue, 2), 'factor', $factor
       )::VARCHAR
FROM size_pick
WHERE year = award_year
"""

# --- Marts ---------------------------------------------------------------------------------

PROCESS_SCORES = """
CREATE OR REPLACE TEMP TABLE process_scores AS
WITH fired AS (
    SELECT s.ocid,
           least(sum(w.weight), $max_score) AS risk_score,
           count(*) AS n_signals,
           list(s.signal_code ORDER BY s.signal_code) AS signal_codes
    FROM signal_rows s JOIN weights w USING (signal_code)
    GROUP BY s.ocid
),
context AS (
    SELECT ocid, count(*) AS n_context_signals,
           list(signal_code ORDER BY signal_code) AS context_signal_codes
    FROM signal_rows WHERE signal_code IN (SELECT unnest($context_codes))
    GROUP BY ocid
)
SELECT b.ocid,
       coalesce(f.risk_score, 0.0) AS risk_score,
       coalesce(f.n_signals, 0)::INTEGER AS n_signals,
       coalesce(f.signal_codes, []::VARCHAR[]) AS signal_codes,
       a.anomaly_score,
       b.award_total, b.year, b.buyer_ruc, b.buyer_name, b.method,
       w.supplier_ruc AS winner_ruc, w.supplier_name AS winner_name,
       CASE
           WHEN w.supplier_ruc IS NULL OR length(w.supplier_ruc) <> 13 THEN 'unknown'
           WHEN substr(w.supplier_ruc, 3, 1) IN ('0', '1', '2', '3', '4', '5') THEN 'natural_person'
           WHEN substr(w.supplier_ruc, 3, 1) = '9' THEN 'company'
           WHEN substr(w.supplier_ruc, 3, 1) = '6' THEN 'public_entity'
           ELSE 'other'
       END AS winner_kind,
       coalesce(c.n_context_signals, 0)::INTEGER AS n_context_signals,
       coalesce(c.context_signal_codes, []::VARCHAR[]) AS context_signal_codes
FROM base b
LEFT JOIN fired f USING (ocid)
LEFT JOIN context c USING (ocid)
LEFT JOIN winners w USING (ocid)
LEFT JOIN anomaly a USING (ocid)
"""

SUPPLIER_PROFILES = """
CREATE OR REPLACE TEMP TABLE supplier_profiles AS
WITH award_rows AS (
    SELECT a.supplier_ruc AS ruc, a.ocid, a.amount, b.buyer_ruc,
           coalesce(TRY_CAST(substr(a.award_date, 1, 10) AS DATE), b.first_award_day) AS award_day
    FROM awards a JOIN base b USING (ocid)
    WHERE a.supplier_ruc IS NOT NULL
),
participation AS (
    SELECT supplier_ruc AS ruc, ocid FROM tenderers WHERE supplier_ruc IS NOT NULL
    UNION
    SELECT ruc, ocid FROM award_rows
),
names AS (
    SELECT ruc, mode(name) AS name FROM (
        SELECT supplier_ruc AS ruc, supplier_name AS name FROM awards WHERE supplier_ruc IS NOT NULL
        UNION ALL
        SELECT supplier_ruc, supplier_name FROM tenderers WHERE supplier_ruc IS NOT NULL
    ) WHERE name IS NOT NULL GROUP BY ruc
),
counts AS (SELECT ruc, count(*) AS n_processes FROM participation GROUP BY ruc),
wins AS (
    SELECT ruc, count(DISTINCT ocid) AS n_wins, sum(amount) AS total_awarded,
           min(award_day) AS first_award_date, max(award_day) AS last_award_date,
           count(DISTINCT buyer_ruc) AS n_buyers
    FROM award_rows GROUP BY ruc
),
by_buyer AS (
    SELECT ruc, buyer_ruc, sum(amount) AS amount, count(DISTINCT ocid) AS n
    FROM award_rows WHERE buyer_ruc IS NOT NULL GROUP BY ruc, buyer_ruc
),
top_buyer AS (
    SELECT ruc, buyer_ruc AS top_buyer_ruc, amount AS top_amount FROM by_buyer
    QUALIFY row_number() OVER (
        PARTITION BY ruc ORDER BY amount DESC NULLS LAST, n DESC, buyer_ruc
    ) = 1
),
won AS (
    SELECT DISTINCT ruc, ocid FROM award_rows
),
risk AS (
    SELECT won.ruc, avg(ps.risk_score) AS mean_risk_score,
           count(*) FILTER (WHERE sb.ocid IS NOT NULL) AS single_bidder_wins
    FROM won
    JOIN process_scores ps USING (ocid)
    LEFT JOIN (SELECT DISTINCT ocid FROM signal_rows WHERE signal_code = 'SINGLE_BIDDER') sb USING (ocid)
    GROUP BY won.ruc
)
SELECT c.ruc, n.name,
       CASE
           WHEN length(c.ruc) <> 13 THEN 'unknown'
           WHEN substr(c.ruc, 3, 1) IN ('0', '1', '2', '3', '4', '5') THEN 'natural_person'
           WHEN substr(c.ruc, 3, 1) = '9' THEN 'company'
           WHEN substr(c.ruc, 3, 1) = '6' THEN 'public_entity'
           ELSE 'other'
       END AS kind,
       c.n_processes::INTEGER AS n_processes,
       coalesce(w.n_wins, 0)::INTEGER AS n_wins,
       coalesce(w.total_awarded, 0.0) AS total_awarded,
       w.first_award_date, w.last_award_date,
       coalesce(w.n_buyers, 0)::INTEGER AS n_buyers,
       t.top_buyer_ruc,
       CASE WHEN w.total_awarded > 0 THEN t.top_amount / w.total_awarded END AS top_buyer_share,
       coalesce(r.single_bidder_wins, 0)::INTEGER AS single_bidder_wins,
       r.mean_risk_score
FROM counts c
LEFT JOIN names n USING (ruc)
LEFT JOIN wins w USING (ruc)
LEFT JOIN top_buyer t USING (ruc)
LEFT JOIN risk r USING (ruc)
"""


SIZE_PICK = SIZE_PICK.replace("__REGISTRY_ELIGIBLE__", REGISTRY_ELIGIBLE)
NEW_SUPPLIER = NEW_SUPPLIER.replace("__REGISTRY_ELIGIBLE__", REGISTRY_ELIGIBLE)
SUPPLIER_NOT_ACTIVE = SUPPLIER_NOT_ACTIVE.replace("__REGISTRY_ELIGIBLE__", REGISTRY_ELIGIBLE)
GHOST_COMPANY_LIST = GHOST_COMPANY_LIST.replace("__REGISTRY_ELIGIBLE__", REGISTRY_ELIGIBLE)
GHOST_COMPANY_LISTED_LATER = GHOST_COMPANY_LISTED_LATER.replace("__REGISTRY_ELIGIBLE__", REGISTRY_ELIGIBLE)

# Winners left out by the restriction above, counted for the build summary (one row per signal).
EXCLUDED_GHOST = """
SELECT count(*) FILTER (WHERE g.notification_day <= b.process_day) AS risk,
       count(*) FILTER (WHERE g.notification_day IS NULL OR g.notification_day > b.process_day) AS context
FROM base b JOIN winners w USING (ocid) JOIN ghosts g ON g.ruc = w.supplier_ruc
WHERE NOT __REGISTRY_ELIGIBLE__
""".replace("__REGISTRY_ELIGIBLE__", REGISTRY_ELIGIBLE)

EXCLUDED_NOT_ACTIVE = """
SELECT count(*) FROM base b JOIN winners w USING (ocid) JOIN sri s ON s.ruc = w.supplier_ruc
WHERE b.method_group <> $catalogue AND NOT __REGISTRY_ELIGIBLE__ AND s.status IS NOT NULL
  AND upper(trim(s.status)) NOT IN (SELECT unnest($active_statuses))
  AND (TRY_CAST(substr(s.suspension_date, 1, 10) AS DATE) IS NULL
       OR TRY_CAST(substr(s.suspension_date, 1, 10) AS DATE) <= b.process_day)
""".replace("__REGISTRY_ELIGIBLE__", REGISTRY_ELIGIBLE)

EXCLUDED_NEW_SUPPLIER = """
SELECT count(*) FROM base b JOIN winners w USING (ocid) JOIN sri s ON s.ruc = w.supplier_ruc
WHERE b.method_group <> $catalogue AND NOT __REGISTRY_ELIGIBLE__ AND b.first_award_day IS NOT NULL
  AND s.activity_start >= DATE '1900-01-01' AND s.activity_start <= b.first_award_day
  AND date_diff('day', s.activity_start, b.first_award_day) < $max_days
""".replace("__REGISTRY_ELIGIBLE__", REGISTRY_ELIGIBLE)
