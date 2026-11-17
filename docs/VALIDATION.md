# Validation against prices, and procedure thresholds

This document has four parts: the analysis plan (written before any outcome was inspected and not edited afterwards), a Deviations section, the generated results, and the threshold method. Nothing here says or implies that Veedor detects corruption or that any company or entity did something wrong. A statistical association between a signal and lower savings describes the dataset as a whole; it is not evidence about any single process. Only aggregate figures appear; no company or entity is named.

<!-- PLAN:BEGIN -->
## Analysis plan (pre-registered; do not edit)

Written on 2026-11-16 before computing any saving-versus-signal quantity. Allowed looks before writing it: table schemas, row counts, signal firing counts, and which fields exist.

### A1. Price outcome

- Sample: processes with `method_group = 'competitive'`, `budget > 0` and `award_total > 0` (budget is the "presupuesto referencial"; `award_total` is the sum of the process awards). Catalogue and direct processes have no competitive saving and are out.
- Outcome: saving ratio `s = 1 - award_total / budget`. Robust variant `s_w`: `s` winsorised at the pooled 1st and 99th percentiles of the sample (computed within each period). Processes with `award_total > budget` stay in (negative saving) and are limited by the winsorisation.
- Periods: exploration 2015-2021, confirmation 2022-2026 (by the `year` column of the lake; 2026 is a partial year). The exploration period is for learning and is reported; the confirmation period is the one that decides what is said. No rule, weight or threshold of the score is changed on the basis of either.

### A2. Which signals are tested, and circularity

Each signal's definition was read (`src/veedor/infrastructure/lake/marts_builder_sql.py`).

| Signal | Class | Treatment |
|---|---|---|
| `SINGLE_BIDDER` | built from the number of tenderers (known at tender close, before award) | primary family |
| `SHORT_TENDER_WINDOW` | built from tender dates (before award) | primary family |
| `NEW_SUPPLIER` | needs the winner's identity (known only after award); no amounts | primary family, marked "post-award information" |
| `SUPPLIER_NOT_ACTIVE` | winner identity and registry status | primary family, marked "post-award information" |
| `GHOST_COMPANY_LIST` | winner identity and list | primary family, marked "post-award information" |
| `RECURRING_COBIDDERS` | winner and losing bidders of the same buyer | primary family, marked "post-award information" |
| `LOW_SAVING` | defined from `award_total / budget`, i.e. from the outcome | **circular**; reported separately, never in the family or the composite |
| `CONTRACT_VS_COMPANY_SIZE` | uses `award_total` | **outcome-dependent**; reported separately like `LOW_SAVING` |
| `BUYER_CONCENTRATION` | uses award amounts summed per buyer-year (includes this process) | **outcome-dependent**; reported separately like `LOW_SAVING` |
| `REPEATED_DIRECT_AWARDS` | direct procedures only | not evaluable on competitive processes |

"Circular set" for the composite below: `LOW_SAVING`, `CONTRACT_VS_COMPANY_SIZE`, `BUYER_CONCENTRATION`.

For each signal the comparison group is processes where the signal could have fired (evaluable), not all processes: `SINGLE_BIDDER`: `n_tenderers` known and the method-category cell is not excluded by design; `SHORT_TENDER_WINDOW`: both tender dates valid with end after start, in a method-year with at least 30 such processes; `NEW_SUPPLIER`, `SUPPLIER_NOT_ACTIVE`, `GHOST_COMPANY_LIST`: winner is a company or public entity (RUC third digit 9 or 6) found in the SRI registry (for the list signal: any such winner); `RECURRING_COBIDDERS`: at least one losing bidder with a RUC. A signal is **not testable** in a period when it has fewer than 30 flagged processes or fewer than 10 distinct flagged buyers there; it is then reported with counts only.

### A3. Estimates per signal and period

1. Counts with and without the signal, and the median of `s` in each group.
2. Raw difference in medians (with minus without) and a 95 % percentile bootstrap interval that resamples buyers (clusters), 1,000 replicates, seed 20260101.
3. Adjusted effect (primary): OLS of `s_w` on the signal indicator, log(budget), and fixed effects for method x year, CPC division (first two digits of `main_cpc`; missing is its own level) and buyer province (`buyer_region`; missing is its own level), fitted on the evaluable group of that signal. Fixed effects are absorbed by iterative demeaning. Standard errors are cluster-robust by buyer (CR1). Effects are in percentage points of budget. The null is no effect; the two-sided test is used and the expected direction (lower saving) gets no one-sided credit.
4. Multiple comparisons: Holm-Bonferroni across the primary family within each period at 0.05 (family-wise error), with Benjamini-Hochberg q-values also shown. The adjusted p-values are reported next to every raw one.
5. Power: the minimum detectable effect at 80 % power is `(z(1 - 0.05/2) + z(0.80)) x SE` and, Holm-conservative, `(z(1 - 0.05/(2m)) + z(0.80)) x SE`, with `m` the number of testable signals in the period.

### A4. Composite score without the circular signals

The production score (weights in `domain/signals/scoring.py`; sum of the weights of distinct fired signals, capped at 100) recomputed without the circular set. A second composite keeps only the signals observable before the award (`SINGLE_BIDDER`, `SHORT_TENDER_WINDOW`). On the whole outcome sample (a signal that cannot fire counts as zero, as in production): Spearman correlation with `s` (95 % buyer-cluster bootstrap, 300 replicates) and the adjusted effect per 10 points of composite (same model as A3, indicator replaced by score / 10). The full production score is reported once for reference, labelled circular.

### A5. Larger external list

Check the official SRI site (sri.gob.ec) for a fuller openly downloadable list than the one used. Load only company (RUC third digit 9) or public-entity (6) rows; never store or print natural-person data. If a larger official set exists, rerun the existing back-test; otherwise keep the existing back-test result unchanged and report what a test with so few positives can and cannot detect (AUC standard error under the null, `0.5 + 2.8 x SE` as the approximate detectable AUC at 80 % power, alpha 0.05 two-sided). Unofficial copies are not used.

### B. Thresholds and bunching

- Thresholds are taken only from official publications, recorded with their source in `docs/THRESHOLDS.md`; a year not verifiable from an official source is marked unverified and excluded. No figure is estimated.
- The amount that determines the procedure is the budget, so budgets are analysed (the award amount is a secondary view). Catalogue processes are excluded.
- For each verified year and threshold `T`: processes of that `year` with budget within +/-20 % of `T`, binned in bins of 1 % of `T`. Counterfactual: a polynomial of degree 3 fitted to the bin counts outside the zone `[0.95 T, 1.05 T)`. Excess mass just below = observed minus counterfactual in `[0.95 T, T]`, divided by the mean counterfactual count per bin (units: bins' worth of mass); missing mass above = the same on `(T, 1.05 T]`. 95 % percentile bootstrap interval resampling buyers, 500 replicates, seed 20260101. Robustness: degree 5, and window +/-30 %. A cell with fewer than 200 processes in the window is reported as "insufficient data".
- Breakdowns by year and by buyer type; buyer type is derived from keywords in the buyer name (municipal government, provincial/parish government, university, health, other) and only aggregate counts are shown.
- Bunching is a description of the distribution of budgets. It is not a verdict on purchasing practice: bunching can come from contract splitting or from real purchasing distortion, and neither is identified here.
- Context only: the threshold mart and endpoints never change a score or enter the signals table.
<!-- PLAN:END -->

## Deviations

Deviations from the plan above, with the reason, are recorded here. Recorded after the first run.

<!-- DEVIATIONS:BEGIN -->
1. **Larger external list (A5): not obtained.** The official SRI page (https://www.sri.gob.ec/empresas-fantasma, checked 2026-11-16) offers the catastro as PDF and XLSX; the XLSX holds 1,112 distinct RUCs (682 with third digit 9) and every one is already in the CSV-based list used (the lake holds 1,113). The CSV on https://www.sri.gob.ec/datasets is therefore the fullest official version found, so the back-test was not rerun; the files are under `data/raw/sri_catastro_fantasma_2026-11-16/` (git-ignored). Unofficial copies were not used. The existing 9-positive result is carried over and its power is stated.
2. **Bunching, pooled and secondary views added (B).** The plan specified per-year estimates. Most year cells have fewer than 200 processes in the window, so estimates pooled over the years with coefficient thresholds (relative to each year's threshold), a pooled award-amount view and a pooled by-buyer-type view were added. Buyer type is pooled only; yearly buyer-type cells are too small.
3. **Not analysed for bunching:** the ínfima/subasta-inversa boundary and every 2026 threshold (ínfima cuantía is not in the lake), the consultancy direct-hiring/lista-corta boundary (direct hiring is not identifiable as the lower side), and 2025 (regime change inside the year).
4. **Signals with no evidence:** `GHOST_COMPANY_LIST` never fires on a process (0 firings, because every listed winner that is a company was listed after the process date) and `SUPPLIER_NOT_ACTIVE` has at most 2 flagged processes in a period; both are "not testable" under the plan's minimum of 30 flagged processes.
<!-- DEVIATIONS:END -->

<!-- RESULTS:BEGIN -->
## Results (generated by `veedor evaluate validation`)

Plan block hash (sha256): `2f8a5dd93c55c981338c966868d9d608dac6fd0c85d72c6f87358a2499cd55b1`. Seed 20260101; bootstrap replicates 1000 (medians) and 300 (Spearman). Sample: 255,097 processes. A signal needs at least 30 flagged processes and 10 distinct flagged buyers in a period to be tested. All figures are aggregates and describe the dataset, not any process.

### Exploration period (2015-2021)

178,420 competitive processes with budget and award; 3,273 buyers; median saving 0.052. Effects are percentage points of budget on the winsorised saving, negative meaning lower saving with the signal. The raw median difference is in saving-ratio units (0.01 = one percentage point).

| Signal | Notes | n with / without | Median saving with / without | Raw median difference (95 % CI) | Adjusted effect, pp (95 % CI) | p | p Holm | q BH | MDE pp (Holm) |
|---|---|---|---|---|---|---|---|---|---|
| `SINGLE_BIDDER` | - | 43,397 / 122,978 | 0.051 / 0.058 | -0.007 (-0.009 to -0.004) | -5.27 (-5.80 to -4.73) | <0.001 | <0.001 | <0.001 | 0.76 (0.91) |
| `SHORT_TENDER_WINDOW` | - | 2,299 / 54,768 | 0.000 / 0.000 | +0.000 (+0.000 to +0.000) | -0.60 (-0.86 to -0.34) | <0.001 | <0.001 | <0.001 | 0.37 (0.44) |
| `NEW_SUPPLIER` | post-award information | 423 / 86,767 | 0.051 / 0.060 | -0.009 (-0.012 to -0.003) | -0.48 (-1.67 to +0.70) | 0.425 | 0.425 | 0.425 | 1.70 (2.02) |
| `SUPPLIER_NOT_ACTIVE` | post-award information | 2 / 87,188 | not testable (fewer than 30 flagged or 10 buyers) | | | | | | |
| `GHOST_COMPANY_LIST` | post-award information | 0 / 87,190 | not testable (fewer than 30 flagged or 10 buyers) | | | | | | |
| `RECURRING_COBIDDERS` | post-award information | 9,038 / 112,376 | 0.055 / 0.058 | -0.003 (-0.028 to +0.010) | +1.14 (+0.41 to +1.86) | 0.002 | 0.004 | 0.003 | 1.03 (1.23) |
| `LOW_SAVING` | circular / outcome-dependent: separate, not corrected | 3,218 / 175,202 | 0.002 / 0.053 | -0.051 (-0.054 to -0.049) | -11.22 (-11.66 to -10.78) | <0.001 | n/a | n/a | 0.63 |
| `CONTRACT_VS_COMPANY_SIZE` | circular / outcome-dependent: separate, not corrected | 3,222 / 175,198 | 0.015 / 0.053 | -0.038 (-0.043 to -0.033) | -0.73 (-1.11 to -0.34) | <0.001 | n/a | n/a | 0.55 |
| `BUYER_CONCENTRATION` | circular / outcome-dependent: separate, not corrected | 1,694 / 176,726 | 0.021 / 0.053 | -0.032 (-0.040 to -0.019) | -1.88 (-2.43 to -1.33) | <0.001 | n/a | n/a | 0.79 |

| Composite | n | Share with score above 0 | Spearman with saving (95 % CI) | Adjusted effect per 10 points, pp (95 % CI) | p |
|---|---|---|---|---|---|
| production weights without the circular signals | 178,420 | 30.303% | -0.1562 (-0.1729 to -0.1400) | -2.34 (-2.54 to -2.14) | <0.001 |
| signals observable before the award only | 178,420 | 25.119% | -0.1648 (-0.1849 to -0.1476) | -2.69 (-2.95 to -2.43) | <0.001 |
| full production score (contains circular signals; reference only) | 178,420 | 33.637% | -0.1908 (-0.2072 to -0.1749) | -2.44 (-2.63 to -2.25) | <0.001 |

### Confirmation period (decisive) (2022-2026)

76,677 competitive processes with budget and award; 2,707 buyers; median saving 0.059. Effects are percentage points of budget on the winsorised saving, negative meaning lower saving with the signal. The raw median difference is in saving-ratio units (0.01 = one percentage point).

| Signal | Notes | n with / without | Median saving with / without | Raw median difference (95 % CI) | Adjusted effect, pp (95 % CI) | p | p Holm | q BH | MDE pp (Holm) |
|---|---|---|---|---|---|---|---|---|---|
| `SINGLE_BIDDER` | - | 13,483 / 59,623 | 0.052 / 0.061 | -0.009 (-0.013 to -0.008) | -8.30 (-8.80 to -7.80) | <0.001 | <0.001 | <0.001 | 0.71 (0.85) |
| `SHORT_TENDER_WINDOW` | - | 768 / 23,220 | 0.000 / 0.010 | -0.010 (-0.013 to -0.008) | -1.46 (-1.94 to -0.99) | <0.001 | <0.001 | <0.001 | 0.68 (0.81) |
| `NEW_SUPPLIER` | post-award information | 415 / 38,843 | 0.055 / 0.064 | -0.008 (-0.011 to -0.005) | -1.43 (-2.51 to -0.34) | 0.010 | 0.020 | 0.014 | 1.55 (1.85) |
| `SUPPLIER_NOT_ACTIVE` | post-award information | 0 / 39,258 | not testable (fewer than 30 flagged or 10 buyers) | | | | | | |
| `GHOST_COMPANY_LIST` | post-award information | 0 / 39,258 | not testable (fewer than 30 flagged or 10 buyers) | | | | | | |
| `RECURRING_COBIDDERS` | post-award information | 2,379 / 56,537 | 0.071 / 0.061 | +0.011 (+0.000 to +0.039) | +0.30 (-0.60 to +1.20) | 0.517 | 0.517 | 0.517 | 1.29 (1.53) |
| `LOW_SAVING` | circular / outcome-dependent: separate, not corrected | 1,071 / 75,606 | 0.000 / 0.060 | -0.060 (-0.060 to -0.057) | -11.70 (-12.23 to -11.18) | <0.001 | n/a | n/a | 0.75 |
| `CONTRACT_VS_COMPANY_SIZE` | circular / outcome-dependent: separate, not corrected | 2,016 / 74,661 | 0.050 / 0.060 | -0.010 (-0.014 to -0.007) | -0.73 (-1.23 to -0.23) | 0.004 | n/a | n/a | 0.71 |
| `BUYER_CONCENTRATION` | circular / outcome-dependent: separate, not corrected | 507 / 76,170 | 0.050 / 0.060 | -0.009 (-0.010 to -0.006) | -3.08 (-4.04 to -2.11) | <0.001 | n/a | n/a | 1.38 |

| Composite | n | Share with score above 0 | Spearman with saving (95 % CI) | Adjusted effect per 10 points, pp (95 % CI) | p |
|---|---|---|---|---|---|
| production weights without the circular signals | 76,677 | 21.969% | -0.1499 (-0.1613 to -0.1383) | -3.73 (-3.93 to -3.52) | <0.001 |
| signals observable before the award only | 76,677 | 18.395% | -0.1746 (-0.1907 to -0.1610) | -4.17 (-4.41 to -3.92) | <0.001 |
| full production score (contains circular signals; reference only) | 76,677 | 25.454% | -0.1903 (-0.2019 to -0.1793) | -3.56 (-3.76 to -3.36) | <0.001 |

### SRI list back-test and what it can detect

Larger official list obtained: **no**. Checked https://www.sri.gob.ec/empresas-fantasma on 2026-11-16. The official XLSX and PDF (Catastro Fantasma) hold 1,112 distinct RUCs, all in the CSV-based list used (1,113 in the lake); no larger official set was found. Only company rows are used in the back-test.

Existing back-test carried over from `eval/backtest.json`: 9 positive companies against 19,837 unlabelled; AUC 0.447 (95 % CI 0.303 to 0.598). Lift in the top 1 % / 5 % / 10 %: 0.00 / 0.00 / 0.00 (precision in the top fraction is lift x prevalence of 0.00045). Under the null the AUC has a standard error of 0.096; at 80 % power only an AUC of about 0.77 or higher could be detected, so the test is inconclusive for any smaller separation.

## Threshold bunching (generated)

Budgets within 20 % of each verified threshold, bins of 1 % of the threshold, a degree-3 counterfactual fitted outside the 5 % zone on each side, buyer-cluster bootstrap. 'Excess (bins)' is the observed minus counterfactual mass in the 5 % just below the threshold, in units of one counterfactual bin; 'excess %' is relative to the counterfactual; 'missing above' is the same comparison in the 5 % just above (positive = fewer processes than the counterfactual). This describes the distribution of budgets; it does not say why purchases sit where they do.

Verified years analysed: 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2026. Excluded: 2025: The regime changed inside the year (coefficient table until June, fixed USD 10,000 from the reform); no single-year table is used. Unverified: none.

- The amount that decides the procedure is the budget (presupuesto referencial), which the lake has for 100 % of competitive processes; award amounts are a secondary view.
- Ínfima cuantía procedures are not in the lake (no such method; competitive budgets start above it), so the lowest threshold cannot be analysed for bunching, only counted just above.
- From the 2025 reform the thresholds are fixed at USD 10,000 and the procedures below (ínfima cuantía) are absent from the lake: 2026 cannot be analysed for bunching.

### Pooled over the years with coefficient thresholds (budget)

| Threshold | n in window | Excess (bins), 95 % CI | Excess % | Missing above % | Degree 5: excess bins | Window 30 %: excess bins |
|---|---|---|---|---|---|---|
| `GS_MENOR_COTIZACION` | 2,513 | +5.86 (+3.64 to +8.42) | +117.3 % | -29.2 % | +6.20 | +6.48 |
| `GS_COTIZACION_LICITACION` | 684 | +3.32 (+1.83 to +5.88) | +66.4 % | +34.7 % | +2.37 | +4.12 |
| `W_MENOR_COTIZACION` | 3,455 | +1.87 (+0.69 to +3.23) | +37.3 % | -14.9 % | +2.27 | +1.96 |
| `W_COTIZACION_LICITACION` | 1,009 | +4.87 (+2.83 to +7.22) | +97.4 % | +44.1 % | +3.99 | +5.78 |
| `C_LISTA_CORTA_CONCURSO` | 239 | +5.99 (+2.86 to +10.21) | +119.7 % | +83.8 % | +5.67 | +7.48 |

Same, on the award amount (secondary view):

| Threshold | n in window | Excess (bins), 95 % CI | Excess % | Missing above % |
|---|---|---|---|---|
| `GS_MENOR_COTIZACION` | 2,197 | +2.67 (+1.57 to +3.74) | +53.5 % | -15.0 % |
| `GS_COTIZACION_LICITACION` | 594 | +0.90 (-0.46 to +3.09) | +18.0 % | +38.0 % |
| `W_MENOR_COTIZACION` | 3,918 | +3.62 (+2.75 to +4.93) | +72.3 % | +16.8 % |
| `W_COTIZACION_LICITACION` | 869 | +2.10 (+0.71 to +3.90) | +42.1 % | +26.1 % |
| `C_LISTA_CORTA_CONCURSO` | 225 | +7.53 (+4.37 to +13.94) | +150.7 % | +80.2 % |

### By buyer type (pooled, budget)

| Threshold | Buyer type | n in window | Excess (bins), 95 % CI | Excess % | Missing above % |
|---|---|---|---|---|---|
| `GS_MENOR_COTIZACION` | provincial or parish government | 321 | +4.09 (+0.00 to +12.93) | +81.7 % | -4.9 % |
| `GS_MENOR_COTIZACION` | municipal government | 632 | +6.74 (+3.98 to +10.45) | +134.7 % | -6.9 % |
| `GS_MENOR_COTIZACION` | university | 60 | insufficient data | n/a | n/a |
| `GS_MENOR_COTIZACION` | health | 96 | insufficient data | n/a | n/a |
| `GS_MENOR_COTIZACION` | other | 1,404 | +5.58 (+1.65 to +10.04) | +111.6 % | -43.0 % |
| `GS_COTIZACION_LICITACION` | provincial or parish government | 47 | insufficient data | n/a | n/a |
| `GS_COTIZACION_LICITACION` | municipal government | 140 | insufficient data | n/a | n/a |
| `GS_COTIZACION_LICITACION` | university | 10 | insufficient data | n/a | n/a |
| `GS_COTIZACION_LICITACION` | health | 9 | insufficient data | n/a | n/a |
| `GS_COTIZACION_LICITACION` | other | 478 | +3.21 (+1.55 to +6.46) | +64.3 % | +30.4 % |
| `W_MENOR_COTIZACION` | provincial or parish government | 456 | -0.95 (-2.19 to +0.65) | -19.1 % | -22.6 % |
| `W_MENOR_COTIZACION` | municipal government | 1,645 | +2.75 (+0.92 to +4.73) | +54.9 % | -12.4 % |
| `W_MENOR_COTIZACION` | university | 53 | insufficient data | n/a | n/a |
| `W_MENOR_COTIZACION` | health | 46 | insufficient data | n/a | n/a |
| `W_MENOR_COTIZACION` | other | 1,255 | +2.01 (+0.52 to +3.87) | +40.2 % | -18.6 % |
| `W_COTIZACION_LICITACION` | provincial or parish government | 95 | insufficient data | n/a | n/a |
| `W_COTIZACION_LICITACION` | municipal government | 532 | +5.37 (+2.38 to +8.32) | +107.5 % | +49.3 % |
| `W_COTIZACION_LICITACION` | university | 26 | insufficient data | n/a | n/a |
| `W_COTIZACION_LICITACION` | health | 8 | insufficient data | n/a | n/a |
| `W_COTIZACION_LICITACION` | other | 348 | +4.80 (+1.19 to +9.63) | +96.0 % | +34.0 % |
| `C_LISTA_CORTA_CONCURSO` | provincial or parish government | 29 | insufficient data | n/a | n/a |
| `C_LISTA_CORTA_CONCURSO` | municipal government | 122 | insufficient data | n/a | n/a |
| `C_LISTA_CORTA_CONCURSO` | university | 3 | insufficient data | n/a | n/a |
| `C_LISTA_CORTA_CONCURSO` | health | 1 | insufficient data | n/a | n/a |
| `C_LISTA_CORTA_CONCURSO` | other | 84 | insufficient data | n/a | n/a |

### By year (budget)

| Year | Threshold | USD | n in window | Excess (bins), 95 % CI | Excess % | Missing above % | Counts below / above (5 % bands) |
|---|---|---|---|---|---|---|---|
| 2015 | `GS_INFIMA_SIE` | 7,263.42 | 0 | not analysable | n/a | n/a | 0 / 321 |
| 2015 | `GS_MENOR_COTIZACION` | 72,634.23 | 327 | +4.52 (+0.99 to +10.07) | +90.4 % | -55.4 % | 61 / 38 |
| 2015 | `GS_COTIZACION_LICITACION` | 544,756.76 | 84 | insufficient data | n/a | n/a | 13 / 3 |
| 2015 | `W_MENOR_COTIZACION` | 254,219.82 | 464 | -1.04 (-2.25 to +0.66) | -20.9 % | -21.2 % | 48 / 78 |
| 2015 | `W_COTIZACION_LICITACION` | 1,089,513.51 | 95 | insufficient data | n/a | n/a | 21 / 8 |
| 2015 | `C_LISTA_CORTA_CONCURSO` | 544,756.76 | 37 | insufficient data | n/a | n/a | 14 / 0 |
| 2016 | `GS_INFIMA_SIE` | 5,967.02 | 0 | not analysable | n/a | n/a | 0 / 251 |
| 2016 | `GS_MENOR_COTIZACION` | 59,670.20 | 245 | +4.98 (+1.12 to +11.48) | +99.6 % | +7.6 % | 59 / 25 |
| 2016 | `GS_COTIZACION_LICITACION` | 447,526.47 | 64 | insufficient data | n/a | n/a | 11 / 5 |
| 2016 | `W_MENOR_COTIZACION` | 208,845.69 | 288 | +0.39 (-1.55 to +3.37) | +7.7 % | -10.9 % | 36 / 35 |
| 2016 | `W_COTIZACION_LICITACION` | 895,052.95 | 98 | insufficient data | n/a | n/a | 28 / 6 |
| 2016 | `C_LISTA_CORTA_CONCURSO` | 447,526.47 | 31 | insufficient data | n/a | n/a | 10 / 0 |
| 2017 | `GS_INFIMA_SIE` | 5,967.02 | 0 | not analysable | n/a | n/a | 0 / 216 |
| 2017 | `GS_MENOR_COTIZACION` | 59,670.20 | 295 | +6.20 (+1.58 to +13.76) | +123.9 % | -41.4 % | 68 / 35 |
| 2017 | `GS_COTIZACION_LICITACION` | 447,526.47 | 50 | insufficient data | n/a | n/a | 13 / 5 |
| 2017 | `W_MENOR_COTIZACION` | 208,845.69 | 396 | +2.24 (-0.05 to +6.12) | +44.8 % | -52.5 % | 68 / 67 |
| 2017 | `W_COTIZACION_LICITACION` | 895,052.95 | 92 | insufficient data | n/a | n/a | 20 / 3 |
| 2017 | `C_LISTA_CORTA_CONCURSO` | 447,526.47 | 23 | insufficient data | n/a | n/a | 5 / 2 |
| 2018 | `GS_INFIMA_SIE` | 6,970.67 | 0 | not analysable | n/a | n/a | 0 / 214 |
| 2018 | `GS_MENOR_COTIZACION` | 69,706.74 | 309 | +2.95 (-0.45 to +7.14) | +59.0 % | -86.3 % | 51 / 51 |
| 2018 | `GS_COTIZACION_LICITACION` | 522,800.57 | 62 | insufficient data | n/a | n/a | 12 / 9 |
| 2018 | `W_MENOR_COTIZACION` | 243,973.60 | 543 | +0.51 (-0.89 to +2.34) | +10.2 % | -12.3 % | 70 / 75 |
| 2018 | `W_COTIZACION_LICITACION` | 1,045,601.15 | 172 | insufficient data | n/a | n/a | 38 / 11 |
| 2018 | `C_LISTA_CORTA_CONCURSO` | 522,800.57 | 19 | insufficient data | n/a | n/a | 7 / 1 |
| 2019 | `GS_INFIMA_SIE` | 7,105.88 | 0 | not analysable | n/a | n/a | 0 / 107 |
| 2019 | `GS_MENOR_COTIZACION` | 71,058.79 | 203 | +15.19 (+6.96 to +40.40) | +303.9 % | -105.1 % | 57 / 29 |
| 2019 | `GS_COTIZACION_LICITACION` | 532,940.92 | 65 | insufficient data | n/a | n/a | 11 / 5 |
| 2019 | `W_MENOR_COTIZACION` | 248,705.76 | 268 | +4.33 (+1.38 to +10.73) | +86.6 % | -18.2 % | 49 / 31 |
| 2019 | `W_COTIZACION_LICITACION` | 1,065,881.83 | 61 | insufficient data | n/a | n/a | 9 / 4 |
| 2019 | `C_LISTA_CORTA_CONCURSO` | 532,940.92 | 21 | insufficient data | n/a | n/a | 6 / 1 |
| 2020 | `GS_INFIMA_SIE` | 7,099.68 | 0 | not analysable | n/a | n/a | 0 / 142 |
| 2020 | `GS_MENOR_COTIZACION` | 70,996.84 | 233 | +6.38 (+1.59 to +13.36) | +127.5 % | -2.8 % | 63 / 27 |
| 2020 | `GS_COTIZACION_LICITACION` | 532,476.31 | 47 | insufficient data | n/a | n/a | 7 / 3 |
| 2020 | `W_MENOR_COTIZACION` | 248,488.94 | 283 | +2.07 (-0.18 to +5.26) | +41.4 % | -14.9 % | 51 / 36 |
| 2020 | `W_COTIZACION_LICITACION` | 1,064,952.62 | 97 | insufficient data | n/a | n/a | 21 / 11 |
| 2020 | `C_LISTA_CORTA_CONCURSO` | 532,476.31 | 22 | insufficient data | n/a | n/a | 3 / 0 |
| 2021 | `GS_INFIMA_SIE` | 6,416.07 | 0 | not analysable | n/a | n/a | 0 / 131 |
| 2021 | `GS_MENOR_COTIZACION` | 64,160.73 | 225 | +7.16 (+1.16 to +14.60) | +143.3 % | -2.3 % | 67 / 24 |
| 2021 | `GS_COTIZACION_LICITACION` | 481,205.45 | 58 | insufficient data | n/a | n/a | 14 / 5 |
| 2021 | `W_MENOR_COTIZACION` | 224,562.54 | 343 | +1.91 (-0.66 to +5.40) | +38.1 % | +25.2 % | 70 / 28 |
| 2021 | `W_COTIZACION_LICITACION` | 962,410.90 | 133 | insufficient data | n/a | n/a | 58 / 2 |
| 2021 | `C_LISTA_CORTA_CONCURSO` | 481,205.45 | 30 | insufficient data | n/a | n/a | 12 / 0 |
| 2022 | `GS_INFIMA_SIE` | 6,779.95 | 0 | not analysable | n/a | n/a | 0 / 72 |
| 2022 | `GS_MENOR_COTIZACION` | 67,799.47 | 115 | insufficient data | n/a | n/a | 26 / 10 |
| 2022 | `GS_COTIZACION_LICITACION` | 508,496.02 | 35 | insufficient data | n/a | n/a | 8 / 2 |
| 2022 | `W_MENOR_COTIZACION` | 237,298.14 | 204 | +7.68 (+1.92 to +21.27) | +153.6 % | +8.9 % | 45 / 15 |
| 2022 | `W_COTIZACION_LICITACION` | 1,016,992.04 | 51 | insufficient data | n/a | n/a | 15 / 1 |
| 2022 | `C_LISTA_CORTA_CONCURSO` | 508,496.02 | 9 | insufficient data | n/a | n/a | 0 / 0 |
| 2023 | `GS_INFIMA_SIE` | 6,300.57 | 0 | not analysable | n/a | n/a | 0 / 76 |
| 2023 | `GS_MENOR_COTIZACION` | 63,005.73 | 239 | +10.01 (+5.64 to +16.71) | +200.2 % | +23.7 % | 91 / 22 |
| 2023 | `GS_COTIZACION_LICITACION` | 472,542.98 | 91 | insufficient data | n/a | n/a | 33 / 4 |
| 2023 | `W_MENOR_COTIZACION` | 220,520.06 | 257 | +4.41 (+1.28 to +8.53) | +88.1 % | +7.4 % | 59 / 25 |
| 2023 | `W_COTIZACION_LICITACION` | 945,085.97 | 77 | insufficient data | n/a | n/a | 24 / 4 |
| 2023 | `C_LISTA_CORTA_CONCURSO` | 472,542.98 | 16 | insufficient data | n/a | n/a | 8 / 0 |
| 2024 | `GS_INFIMA_SIE` | 6,659.36 | 0 | not analysable | n/a | n/a | 0 / 101 |
| 2024 | `GS_MENOR_COTIZACION` | 66,593.64 | 322 | +3.10 (+0.47 to +6.20) | +62.1 % | -49.5 % | 69 / 52 |
| 2024 | `GS_COTIZACION_LICITACION` | 499,452.30 | 128 | insufficient data | n/a | n/a | 33 / 10 |
| 2024 | `W_MENOR_COTIZACION` | 233,077.74 | 409 | +2.76 (+0.21 to +6.65) | +55.2 % | -28.3 % | 66 / 63 |
| 2024 | `W_COTIZACION_LICITACION` | 998,904.59 | 133 | insufficient data | n/a | n/a | 25 / 8 |
| 2024 | `C_LISTA_CORTA_CONCURSO` | 499,452.30 | 31 | insufficient data | n/a | n/a | 10 / 0 |
| 2026 | `GS_INFIMA_SIE` | 10,000.00 | 0 | not analysable | n/a | n/a | 0 / 60 |
| 2026 | `W_INFIMA_LICITACION` | 10,000.00 | 0 | not analysable | n/a | n/a | 0 / 6 |
| 2026 | `C_INFIMA_CONCURSO` | 10,000.00 | 0 | not analysable | n/a | n/a | 0 / 0 |
<!-- RESULTS:END -->

## Reading the results (written after the run; not part of the plan)

- **Price outcome.** In the confirmation period (2022-2026) three of the six testable signals in the primary family are associated with lower savings after adjusting for method x year, product class, province and budget, and the association survives the Holm correction: `SINGLE_BIDDER`, `SHORT_TENDER_WINDOW` and `NEW_SUPPLIER`. `RECURRING_COBIDDERS` shows no association in the confirmation period, and in the exploration period it went the opposite way (higher savings); that is an adverse result for the idea that the signal tracks weaker price competition. `SUPPLIER_NOT_ACTIVE` and `GHOST_COMPANY_LIST` cannot be tested at all.
- **What the association means.** A single bidder cannot produce a competitive price reduction, so a lower saving there is close to the definition of competition rather than independent evidence. The raw median difference is much smaller than the adjusted mean difference because many flagged processes sit at exactly zero saving. None of this is evidence about any individual process.
- **Circular signals.** `LOW_SAVING`, `CONTRACT_VS_COMPANY_SIZE` and `BUYER_CONCENTRATION` use the award amount; their association with saving is partly or wholly mechanical and is reported only for completeness.
- **Composite.** Without the circular signals the composite has a small negative rank correlation with saving (about -0.15 in both periods) and about -2 to -4 percentage points of saving per 10 points; it is driven mostly by `SINGLE_BIDDER`, the heaviest weight.
- **Registry-based signals and the SRI list.** The back-test against the SRI list has 9 positives; it can only detect an AUC of roughly 0.77 or higher, so its 0.447 is inconclusive, not a negative or positive result. No larger official list exists to improve this.
- **Bunching.** Budgets are over-represented just below the menor-cuantía/cotización and other coefficient thresholds relative to a smooth counterfactual in the pooled data, with intervals above zero for most thresholds. This is a description. A procedure-composition change at a threshold (menor cuantía below, cotización above) can itself bend the budget density, which a polynomial counterfactual does not model, so the size of the excess should not be over-read. It does not say whether purchases were split or the needs were real.

