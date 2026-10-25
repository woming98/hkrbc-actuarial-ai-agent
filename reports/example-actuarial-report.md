# HK RBC — Illustrative actuarial movement report

Report ID: `2031d5a4-d87e-49df-b7db-2396da466949`

Generated (UTC): 2026-10-25T02:02:28.973941+00:00

**Synthetic data • Educational approximation • Not a regulatory capital return**

## Purpose and scope

Compare two synthetic asset portfolios using deterministic valuation, illustrative rate, credit and equity stresses, and diversification-aware attribution. This asset-only model does not calculate statutory HK RBC prescribed capital or capital resources.

## Deterministic results

Status: **COMPLETE** · Calculation version: `1.0.0`

Valuation dates: 2025-12-31 → 2026-09-30

| Measure | HKD |
|---|---:|
| Opening illustrative capital | 20,224,927.84 |
| Closing illustrative capital | 22,615,906.43 |
| Actual capital movement | 2,390,978.59 |
| Explained movement | 2,390,978.59 |
| Unexplained residual | 0.00 |

| Risk module | Opening | Closing | Standalone change | Shapley allocation |
|---|---:|---:|---:|---:|
| Rate | 7,307,753.32 | 7,112,135.44 | -195,617.88 | -113,353.33 |
| Credit | 7,307,753.32 | 7,112,135.44 | -195,617.88 | -144,084.41 |
| Equity | 12,000,000.00 | 15,000,000.00 | 3,000,000.00 | 2,648,416.33 |

## Counterfactual factor bridge

Bridge status: **COMPLETE**. Date ageing is applied first; the three remaining factor replacements are averaged over all six orderings. This is model attribution, not reconstructed transactions or investment returns.

| Factor | Attributed movement (HKD) |
|---|---:|
| Date ageing at opening quotes | -924,090.62 |
| Holdings And Equity Value | 3,165,983.67 |
| Risk Free Yield | 277,386.92 |
| Credit Spread | -128,301.37 |
| Unexplained factor-bridge residual | 0.00 |

Equity/cash value changes combine quantities, prices and flows. Entry/exit bonds retain their sole observed quote. Unknown coupon/maturity settlement and changed instrument terms block completion under the default policy.

## Risk-module movement allocation

- Rate: Change in bond exposure, remaining cashflows and yields under +/-100 bp rate stress. Shapley contribution HKD -113,353.33; material: True.
- Credit: Change in bond exposure, remaining cashflows and yields under +100 bp spread stress. Shapley contribution HKD -144,084.41; material: True.
- Equity: Change in equity market value under the illustrative 30% equity shock. Shapley contribution HKD 2,648,416.33; material: True.

## Validation

| Check | Result | Detail |
|---|---|---|
| opening_validation | PASS | Opening portfolio deterministic checks. |
| closing_validation | PASS | Closing portfolio deterministic checks. |
| movement_reconciliation | PASS | Exact Shapley allocation residual: HKD 0.0000000000; tolerance HKD 0.01. |
| unexpected_movement_review | PASS | Review required if absolute change exceeds HKD 100000 and relative change exceeds 50%; opening zero with material increase also requires review. |
| factor_bridge_validation | PASS | Date-first bridge plus exact holdings/yield/spread Shapley; unknown coupon/maturity settlement blocks attribution. |

## Methodology and assumptions

Bonds use annual maturity-anniversary cashflows discounted at an effective risk-free yield plus credit spread, with actual/365.25 time. Prices are dirty values without accrued-interest or settlement modelling. Rate capital is the larger aggregate portfolio loss under parallel up/down stresses; spread capital and equity capital use fixed illustrative shocks. Cash has no modelled charge.

Aggregate capital is sqrt(cᵀRc) using the documented illustrative positive semidefinite correlation matrix. Exact Shapley allocations across the three module replacements reconcile the nonlinear opening-to-closing movement. Attribution depends on this model and does not establish economic causality.

## Regulatory references

Contextual references below do not calibrate the illustrative model or establish current compliance.

- [Insurance (Valuation and Capital) Rules, L.N. 62 of 2024 — Capital adequacy thresholds](https://www.ia.org.hk/en/legislative_framework/overview/files/es22024281862.pdf) — Part 2, rule 5(1), Gazette page B647; version `2024-05-03-baseline`; published 2024-05-03; reviewed 2026-10-24. Historical baseline only; requires insurer applicability, valuation date, variations/relaxations and current official text. Does not establish a complete regulatory calculation.
- [Insurance (Valuation and Capital) Rules, L.N. 62 of 2024 — Minimum capital amount baseline](https://www.ia.org.hk/en/legislative_framework/overview/files/es22024281862.pdf) — Part 2, rule 5(3), Gazette page B647; version `2024-05-03-baseline`; published 2024-05-03; reviewed 2026-10-24. Do not apply the 50% baseline if an insurer-specific variation or relaxation applies.
- [Public Disclosure Requirements for the First Financial Year Adopting RBC Regime, Annex 1 — Capital composition disclosure fields](https://www.ia.org.hk/en/legislative_framework/circulars/reg_matters/files/Circular_20250808_Annex_1.pdf) — Section 4, Capital adequacy, paragraphs (a)–(b), printed pages 4–5; version `2025-08-08-baseline`; published 2025-08-08; reviewed 2026-10-24. A disclosure template establishes fields, not capital eligibility, deductions, limits or calculation formulas. Numeric tier caps are omitted because operative rule 7 was not independently verified from primary text in this session.

## Limitations and review

No liabilities, taxes, operational risk, counterparty default model, matching adjustment, currency risk, rating-specific factors, regulatory floors, or full prescribed aggregation are implemented. Coupon conventions and flat curves are simplified. Large movements require actuarial review even where arithmetic reconciliation passes. Failed validation prevents completion. This prototype is not a certified compliance solution.

## Audit and calculation records

The local SQLite audit records demo identity, UTC timestamps, tool versions, validation status, provider, document versions accessed and report identifier. It excludes raw prompts and portfolios. Logs are local and are not tamper-proof.

Deterministic calculation ID: `movement-ad0212953f517237`. The accompanying JSON export contains every synthetic input, per-asset output, function/version, assumptions, validations and limitations. Use both files for technical review.

Combined analysis ID: `analysis-98631ac490f8b6e8` · Workflow version: `0.2.0` · Factor bridge ID: `attribution-23963dcbb5846a0e`.
