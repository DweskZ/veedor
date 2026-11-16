# Methodology: Signals v1

Veedor reports **risk indicators**, never accusations. A fired signal says that a field in the
public data is atypical under a stated rule; it does not say that anything improper happened.
Every rule below is implemented as set-based DuckDB SQL over the Parquet lake
(`src/veedor/infrastructure/lake/marts_builder_sql.py`); its parameters live in
`src/veedor/domain/signals/parameters.py` and the catalogue in
`src/veedor/domain/signals/definitions.py`. Each fired signal stores `value`, `threshold` and an
`evidence_json` with the concrete facts needed to verify it against the source record.

## Conventions

- **Method groups** come from `processes.method_group` (see `flatten.py`): `competitive`, `direct`,
  `catalogue`, `other`, `no_tender_block`, `unknown`.
- **Year** is `processes.year` (year of `tender_start`, or of the release date when absent).
- **Method-year** = one procurement method in one year. Statistical thresholds are computed per
  method-year from the data, never hard-coded. A method-year with fewer than **30** processes gets
  no threshold (recorded as `skipped_small_group` in the build summary).
- **Winner of a process** = the supplier in `awards` with a RUC and the **largest award amount**.
  Amounts are null when one award lists several suppliers (the source does not split them); then the
  smallest RUC breaks the tie, so the choice is deterministic but arbitrary among co-awardees. All
  `winner_*` columns, and every signal that talks about "the winner", use this single supplier.
- **Supplier kind** comes from the third digit of the RUC: `0`-`5` natural person, `9` company,
  `6` public entity, other digits `other`, missing or malformed RUC (or no winner at all) `unknown`,
  never null, so the API can mask by default. Internal marts keep real
  names; masking happens at the API boundary.
- Dates in the lake are ISO strings with offset; calendar dates use the first 10 characters (local
  Ecuador date). Tender windows use absolute timestamps.
- Each (process, signal) pair appears at most once in `process_signals`.
- **Risk and context signals.** `process_signals.kind` is `risk` or `context`. Context signals are
  informational, weigh 0, and never change `risk_score`, `n_signals` or `signal_codes`; they are
  counted separately in `n_context_signals` / `context_signal_codes` of `process_scores`.

## Registry facts and natural persons

Registry-derived signals (`NEW_SUPPLIER`, `SUPPLIER_NOT_ACTIVE`, `GHOST_COMPANY_LIST`,
`GHOST_COMPANY_LISTED_LATER`, `CONTRACT_VS_COMPANY_SIZE*`) are computed **only for winners that are
companies (RUC third digit 9) or public entities (6)**. For natural persons, and for winners
without a valid RUC, they never fire, whether risk or context. Reason: data protection. The SRI
list includes natural persons, and attaching a listing, a tax status, a suspension date or an
activity start date to a process makes that information about an identifiable individual public
(the process is public and the resolution number is a direct key into the SRI list), even if the
winner's name is masked. Veedor does not publish registry information about individuals. The count
of matches left out is reported in `build_summary.json` (`signal_details`).

## Signals

### SINGLE_BIDDER
- **Rule**: `n_tenderers = 1`.
- **Scope**: `competitive` processes with `n_tenderers` informed. Direct and catalogue purchases
  have no competition to measure and are excluded. "Contratacion directa" (consultancy direct
  contracting) is classified as `direct` by the lake, so it is out of scope already.
- **Excluded by design (data-derived)**: a method-category cell with at least 30 processes where at
  least 99.9 % have exactly one tenderer records no competition, so one bidder is not informative.
  In the real lake this removes **Menor Cuantia for goods (2,863 processes, 100 %) and services
  (12,839 processes, 99.95 %)**; every other cell is below 52 %. The 99.9 % cut is a judgement call
  (the six services processes with two tenderers are treated as clerical); the excluded cells are
  listed in `build_summary.json` under `signal_details.SINGLE_BIDDER`. Menor Cuantia **works** stay
  in scope (25.8 % single-bidder).
- **Lista corta** (consultancy short lists): 25-66 % single-bidder by year (50.8 % overall, falling
  from 64 % in 2015 to 31 % in 2025). It varies across years and is not near 100 %, so a single
  tenderer is still informative; it is kept, but its base rate is high and the signal should be read
  against it.
- **Lotteries**: the "Sorteo" award mechanism for works cannot be identified in the data (one
  process description in 2.25 M mentions it), so lottery-awarded Menor Cuantia works are *not*
  removed and remain a known false-positive source.
- **Fields**: `method_group`, `method`, `category`, `n_tenderers`.
- **Sanity check against the lake** (single-bidder processes / processes with `n_tenderers`
  informed): Subasta Inversa Electronica 40,143 / 177,857 (22.6 %), Cotizacion 3,749 / 14,729
  (25.5 %), Licitacion 1,937 / 9,750 (19.9 %), Menor Cuantia 9,744 / 53,446 (18.2 % of all, 25.8 %
  of works; it was 25,440 / 47.6 % before the by-design exclusion).
- **False positives**: sole distributors or sole manufacturers legitimately bid alone; thin local
  markets; lottery awards of Menor Cuantia works (not identifiable).

### SHORT_TENDER_WINDOW
- **Rule**: `tender_end - tender_start` (days) is strictly below the 5th percentile of its
  method-year.
- **Scope**: `competitive` processes with both dates and `tender_end > tender_start` (equal or
  negative windows are treated as data errors and ignored). Narrower than the contract ("rows with
  both dates"): direct procedures also carry dates, but "short window" is meaningless without
  competition. Subasta Inversa Electronica has no `tender_end` in the source, so it never fires.
- **Threshold**: `quantile_cont(days, 0.05)` per method-year (linear interpolation), minimum 30
  processes.
- **False positives**: legal minimum periods differ by object and amount; urgent but legitimate
  purchases; clerical errors in dates. Where many processes share the legal minimum (e.g. the
  percentile sits on a repeated value), strict "below" keeps the signal limited to windows shorter
  than that.

### LOW_SAVING
- **Rule**: `award_total / budget >= max(P95, 0.99)`, with `P95` the 95th percentile of the ratio in
  its method-year.
- **Scope**: `competitive` processes with `budget > 0` and `award_total > 0`.
- **Mass-point guard (deviation, added by us)**: when more than **10 %** of a method-year already
  sits at or above that threshold, the percentile is a mass point (awards equal to the budget by
  design) and being there is not atypical, so the method-year is **not evaluated**
  (`skipped_mass_point`). In practice this removes Menor Cuantia (66-79 % of processes at 100 % of
  budget), most Cotizacion and Lista corta years. The threshold table in `build_summary.json` lists
  every skipped method-year with its share. Without the guard the signal would fire on most
  Menor Cuantia processes and carry no information.
- **False positives**: budgets set from market quotes legitimately equal the award; fixed-price
  items (regulated prices, insurance premiums) leave no room for savings.

### NEW_SUPPLIER
- **Rule**: `1900-01-01 <= activity_start_date <= first_award_date` and the difference is
  **0 to 179 days** (`< 180`).
- **Scope**: non-catalogue processes whose winner (company or public entity) matches
  `suppliers_sri.ruc`. Natural persons are not evaluated: this removed 1,291 of 2,598 firings
  (2,598 -> 1,307), kept consistent with the other registry signals because an individual's
  activity start date is registry information about that individual. Catalogue purchases
  are excluded because the supplier was selected earlier through a framework agreement.
- **Fields**: `suppliers_sri.activity_start_date`, `processes.first_award_date`.
- **Data handling**: some SRI start dates are implausible (the earliest is year 1541); dates before
  1900 are ignored. A start date after the award date is not fired (it usually reflects a
  re-registration, not a company created after winning). `SRI` keeps one row per RUC (head
  establishment).
- **False positives**: public entities and new companies created for a specific legitimate
  project; a new RUC for an existing business (e.g. change of legal form).

### SUPPLIER_NOT_ACTIVE
- **Rule**: the winner's **current** SRI status is not `ACTIVO` (values seen: `PASIVO`,
  `SUSPENDIDO`) **and** the data does not show that the supplier was still active at the process
  date:
  - `suspension_date` after the process date: **does not fire** (the registry itself shows the
    supplier was active then);
  - `suspension_date` on or before the process date: fires, `"timing": "suspended_before_process"`;
  - no parseable `suspension_date`: fires with `"timing": "unknown"`, meaning the timing cannot be
    established and the text must say so.
- **Process date** (fallback order): `first_award_date`, else `date_signed`, else `tender_start`,
  else `release_date`.
- **`restart_date` is not used.** In the registry it is earlier than `suspension_date` for 99.9 % of
  non-active RUCs (a past reactivation followed by a later suspension), and `status` is already the
  current state, so it cannot establish "suspended, then restarted before the process".
- **Scope**: non-catalogue processes whose winner (company or public entity) matches the SRI
  registry. Natural persons are not evaluated (an individual's tax status and suspension date is
  not published): 32 -> 16 firings.
- **Caveat**: status is the one in the file retrieved on 2026-11-16, not a history. All
  non-active RUCs in the retrieved file carry a `suspension_date`, so the `unknown` case is
  currently empty; it is kept for future registry loads. The suspension date is the registry's
  own date; it is not independently verified.
- **Effect of the timing rule on the real lake**: 27,291 non-catalogue processes had a non-active
  winner; 27,259 were suppressed because the suspension came after the process date, 32 fire.

### GHOST_COMPANY_LIST (risk) and GHOST_COMPANY_LISTED_LATER (context)
- **Rule**: the winner's RUC appears in the catalogue the SRI published of contributors qualified as
  "empresas fantasmas". Wording: "aparece en el listado publicado por el SRI"; a listing is a
  registry fact, not a finding about a contract.
- **Timing split**: `GHOST_COMPANY_LIST` (risk, weight 30) fires only when the SRI `notification_date`
  is **on or before the process date** (process date as under SUPPLIER_NOT_ACTIVE): the listing
  existed when the buyer awarded. When the notification is **after** the process date, or has no
  date, `GHOST_COMPANY_LISTED_LATER` (context, weight 0) is emitted instead, because the buyer could
  not have known. Real lake after the natural-person restriction: 0 risk firings and 44 context firings (before it:
  6 and 159).
- **Scope**: all methods, including catalogue (a listing is categorical, not a rate), but only
  company or public-entity winners. Natural-person and unidentified winners on the list produce no
  signal of either kind (6 would have been risk and 115 context; real lake now: 0 risk and 44
  context).
- **Evidence**: `resolution`, `notification_date`, `qualification_detail`, `challenge_state`,
  `process_date`, and `listed_after_process` (risk) or `timing` = `listed_after_process` /
  `notification_date_missing` (context). The source's `publication_date` is always null.
  Qualifications can be challenged: only a minority are marked as ratified and some listed RUCs are
  active today; the snapshot has no history.

### BUYER_CONCENTRATION
- **Rule**: for a buyer-year, the supplier received at least **30 %** of the buyer's awarded
  amount, the buyer-year total is at least **USD 100,000**, the buyer-year has at least **3**
  awarded processes, **and no single process of that supplier reaches 30 % of the buyer-year total
  by itself**.
- **Why the last condition (refinement)**: without it a single large contract that dominates a
  small buyer-year (e.g. one process = 82 %) fires the signal, which then measures contract size,
  not repeated selection of the same supplier. Counted on the real lake, over the buyer-year-
  supplier pairs that satisfy the contract rule (9,831 pairs, 13,496 processes): one award alone
  crosses the threshold in 8,648 pairs (88 %); requiring the supplier to have at least 2 awards
  would still leave 5,881 processes and at least 3 awards 2,867, but both keep cases where one big
  award does the work. Excluding the single-award case leaves 3,231 processes and is the option
  that matches the signal's meaning. The 30 % is the signal's own threshold, not a new benchmark.
- **Scope**: non-catalogue processes; amounts from `awards.amount` greater than 0 (awards that list
  several suppliers have a null amount and are not counted on either side of the ratio). The signal
  fires on every process in which that supplier received an amount in that buyer-year; if two
  concentrated suppliers share a process, the one with the larger share is reported.
- **Evidence**: supplier and buyer-year amounts, share, `n_awards_buyer_year`, `supplier_awards`
  and `largest_supplier_process_share`.
- **False positives**: buyers that legitimately depend on one provider (utilities, a multi-year
  works programme split in contracts, public entity suppliers); small buyers with few purchases.

### REPEATED_DIRECT_AWARDS
- **Rule**: the same buyer, the same winner and the same 5-digit CPC prefix have at least **3**
  `direct`-group processes inside a window of **90 days**. A process fires if some 90-day window
  that contains it holds at least 3 such processes. The process date is `first_award_date`
  (falling back to `tender_start`).
- **False positives**: framework-like recurring services (maintenance, communications, legal
  advice) procured in instalments under a single exception ground; legitimate sole suppliers.

### RECURRING_COBIDDERS
- **Rule**: in `competitive` processes of the same buyer, the winner and the same losing tenderer
  (a different RUC, taken from `tenderers`) met in at least **5** processes.
- **Evidence**: the pair with most meetings in the process and how many recurring co-bidders it has.
- **False positives**: local markets with few suppliers in a category naturally meet often;
  associated businesses that are legitimately active in the same niche.

### CONTRACT_VS_COMPANY_SIZE (risk) and CONTRACT_VS_COMPANY_SIZE_SAME_YEAR (context)
- **Rule**: `award_total > 3 x revenue`, where revenue is the company's **sales revenue**
  (`company_financials.revenue`, from `ingresos_ventas`) of the latest financial year **strictly
  before the award year** with revenue greater than zero (award year = year of the process date).
- **Why strictly before**: revenue of the award year itself can include the contract being tested,
  so the comparison is circular. If a company has no earlier year but has revenue for the award
  year, the same comparison is emitted as `CONTRACT_VS_COMPANY_SIZE_SAME_YEAR` (context, weight 0,
  lower confidence), with `comparison: same_year` in the evidence. Risk evidence carries
  `revenue_year`, `award_year` and `years_before_award` (the prior year can be several years old).
- **Effect on the real lake**: the previous rule (latest year at or before the award year) fired
  4,023 times, 2,859 of them against the award year itself. Using the prior year fires **5,957**
  times (prior-year revenue is usually smaller, because companies grow) and the same-year-only
  comparison yields **614** context firings. Firings resting on revenue under USD 1,000:
  1,361 of 5,957 (counted in `build_summary.json`).
- **Why `revenue` and not `total_income`**: `revenue` follows the contract and covers 2008-2025;
  `total_income` only exists from 2010 and mixes in non-operating income.
- **Tiny positive revenues are kept.** Positive revenues in the data have percentiles
  P1 = 5, P5 = 500, P10 = 3,396, P25 = 24,213, P50 = 132,209 USD; 6.2 % of positive rows are under
  USD 1,000. The data alone cannot tell dormant or very small companies (plausible) from entry
  errors or units mistakes (noise), and no external benchmark is invented, so the rule does not
  exclude them; the count of firings under USD 1,000 is reported in the build summary and the
  evidence always shows revenue and year so a reviewer can discount them.
- **Data handling**: `revenue <= 0` or null is **unknown, not zero** (zeros are 80-99 % of rows in
  2008-2011 and 28-41 % from 2012 and look like missing data). `(ruc, year)` is not unique (some
  RUCs have more than one `expediente`): the largest revenue per `(ruc, year)` is used. A financial
  year after the award year is never used.
- **Scope**: non-catalogue processes whose winner (company or public entity) has a positive
  revenue. The financials come from the companies regulator: in the real lake every firing is a
  company winner and the restriction removes none (only 6 natural-person RUCs have positive
  revenue and none won), but it is applied explicitly so it holds for future loads.
- **False positives**: revenue of an earlier, smaller year; consortia and construction firms whose
  turnover is irregular; amounts that cover several years.

## Score

`risk_score = min(100, sum of weights of the distinct fired signals)`, computed in
`domain/signals/scoring.py`:

| signal | weight |
|---|---|
| SINGLE_BIDDER | 20 |
| SHORT_TENDER_WINDOW | 10 |
| LOW_SAVING | 10 |
| NEW_SUPPLIER | 15 |
| SUPPLIER_NOT_ACTIVE | 15 |
| GHOST_COMPANY_LIST | 30 |
| BUYER_CONCENTRATION | 15 |
| REPEATED_DIRECT_AWARDS | 15 |
| RECURRING_COBIDDERS | 15 |
| CONTRACT_VS_COMPANY_SIZE | 15 |

**The weights are judgement calls pending calibration.** They are not fitted to labelled
outcomes. They only encode an ordering: signals based on a registry listing weigh most,
bidder-structure and relationship signals weigh in the middle, and signals that are very common
or that often reflect rules of the procedure (short window, low saving) weigh least. Context signals (`GHOST_COMPANY_LISTED_LATER`, `CONTRACT_VS_COMPANY_SIZE_SAME_YEAR`) have weight 0 and are
not in this table. Processes
that cannot be evaluated by a signal (missing field, missing registry match, out-of-scope method)
simply do not fire it; a score of 0 means "no signal fired", not "low risk". The maximum possible
sum is above 100, hence the cap.

## Anomaly score (separate from the risk score)

`anomaly_score` is an Isolation Forest (scikit-learn, 200 trees, `random_state=42`) fitted **per
procurement method** on competitive processes with `budget > 0`. Features: `ln(1 + budget)`,
`award_total / budget`, `n_tenderers`, `n_enquiries` and the tender window in days. A feature is
used for a method only if at least 90 % of its rows have it (so the window is absent for Subasta
Inversa Electronica); rows with a missing used feature, and methods with fewer than 500 usable rows,
get a null score. The value is `-score_samples`: higher means more atypical, comparable within a
method rather than across methods. It never changes `risk_score`. It measures statistical
unusualness only, and flags legitimate extremes (very large works) as well.

## Marts and the build summary

- `process_signals.parquet`: one row per fired signal; `kind` is `risk` or `context`.
- `process_scores.parquet`: one row per process in the lake (zeros included); `n_signals` and
  `signal_codes` count risk signals only, `n_context_signals` and `context_signal_codes` the
  context ones; `winner_kind` is `unknown` when there is no winner RUC.
- `supplier_profiles.parquet`: one row per RUC seen as tenderer or awardee. `n_wins` counts
  processes where the supplier appears in `awards`; `total_awarded` sums amounts that are not null;
  `top_buyer_*` use awarded amounts; `single_bidder_wins` counts won processes where SINGLE_BIDDER
  fired; `mean_risk_score` averages `risk_score` over won processes.
- `build_summary.json`: rows per mart, fired count per signal, thresholds per method-year (with
  status), registry coverage, anomaly report, signals not computed with the reason, build time and
  lake row counts. A registry-dependent signal whose source table is missing is reported as
  `not computed: source table missing` and produces no rows, never zeros.

## Limits

- Emergency procurement, catalogue purchases (1.86 M of 2.25 M processes) and procedures with no
  tender block are **outside the competition analysis**: they have no bidder data, so bidder and
  window signals never fire for them.
- Registry facts are **current**, not historical (SRI status, listing snapshot). Registry
  matching depends on RUC extraction from OCDS party ids; absence from a registry means only that
  the RUC was not found in the retrieved files.
- Financial data covers only companies supervised by the Superintendencia de Companias.
- Winner selection among several suppliers in one award is by amount, otherwise arbitrary.
- No signal is validated against labelled cases. Thresholds describe typicality within the data,
  not legality. Every alert needs human review.
