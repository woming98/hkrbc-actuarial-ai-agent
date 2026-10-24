# Actuarial methodology

Every amount is HKD. Every capital amount is an **internal illustrative asset-only approximation**, not prescribed HK RBC capital, a solvency ratio, or capital resources. Stress calibration and the correlation matrix are not regulatory parameters.

## Input contract

CSV header order is fixed:

```text
asset_id,asset_type,currency,valuation_date,market_value,face_value,coupon_rate,yield_rate,maturity_date,credit_spread_bps
```

Types are `bond`, `equity` or `cash`; currency is HKD; dates use YYYY-MM-DD. A file has one valuation date and unique nonempty ASCII identifiers. Each bond requires a positive face, coupon in [0,1], annual effective risk-free yield, nonnegative spread in basis points and future maturity (maximum 100 years). Yield must exceed -95% before stress. Equities/cash require nonnegative market value; irrelevant fields must be blank. A supplied bond value must reconcile to model PV within max(HKD0.01, PV×1e−8); otherwise leave the field blank and derive PV. Zero holdings are allowed for equity/cash. Files are limited to 2MB and 10,000 rows.

## Valuation and sensitivities

Future annual coupon dates fall on maturity anniversaries; leap-day anniversaries use the last valid day. Exclude payments on/before valuation date. For time `t_i = actual_days/365.25`, cashflow `CF_i` and combined annual effective yield `y = risk_free_yield + spread_bps/10000`:

```text
PV = Σ CF_i (1+y)^(-t_i)
Macaulay duration = Σ t_i CF_i (1+y)^(-t_i) / PV
Modified duration = Macaulay duration / (1+y)
DV01 = PV × modified duration × 0.0001
```

This is a dirty-PV convention with full annual coupons even in a short first interval. There is no accrued-interest/clean-price, settlement calendar, recovery or optionality model. The public maturity-in-years helper uses backward annual periods; portfolio valuation uses actual dated anniversaries. They are deliberately distinct interfaces.

Key-rate nodes are 1, 2, 5, 10, 20 and 30 years. Linearly interpolated node weights partition unity, clamping to endpoint weights outside the grid. KRD is the exact local derivative for each zero-yield node, normalized by PV. KRD sums to modified duration under this annual-effective flat-curve convention. It is not a calibrated term-structure model.

## Illustrative risk modules

Reprice each bond under ±100bp risk-free yield and +100bp credit-spread shocks. Rate capital is max(0, aggregate rate-up loss, aggregate rate-down loss). Credit capital is the aggregate positive spread-stress loss. Equity capital is 30% of equity market value. Cash is unchanged and has no modelled charge. Riskless cash cannot cancel small risky losses through subtracting large portfolio totals; per-asset losses are summed with compensated summation.

Module vector order is rate, credit, equity. Aggregate capital uses `sqrt(cᵀRc)` with:

| R | Rate | Credit | Equity |
|---|---:|---:|---:|
| Rate | 1 | 0.25 | 0.25 |
| Credit | 0.25 | 1 | 0.50 |
| Equity | 0.25 | 0.50 | 1 |

The matrix is symmetric positive definite. A separate Cholesky-norm identity verifies aggregation; bounds verify capital is between the largest module and their sum. This matrix is an internal teaching choice.

## Movement reconciliation

Closing date must be later than opening date. Recalculate both dates from their own holdings, cashflows, market values, yields and spreads. For each of six possible module replacement orders, replace opening modules by closing modules and record marginal aggregate changes. Their mean is exact three-player Shapley attribution:

```text
Σ attribution_i = aggregate_closing − aggregate_opening
unexplained_residual = actual_movement − Σ attribution_i
```

This reconciles nonlinear diversification without summing standalone module changes. Raw changes, diversification-benefit movement, new/removed asset IDs and exposure totals remain visible. Descriptions identify possible module drivers; they do not claim transaction-level causal decomposition. Exposure, yield, ageing and portfolio mix are not separately isolated. Shapley allocations depend on the specified aggregation and counterfactual hybrid vectors.

Reconciliation tolerance is HKD0.01 (relative tolerance 1e−10). A movement above HKD100,000 **and** above 50% of opening capital triggers an unresolved actuarial-review check and blocks completion, even when it reconciles. A material increase from zero also blocks completion. Thresholds are demonstration choices, with no reviewer override implemented.

## Scenario demonstration

A local seeded Python `random.Random` generates 1–1,000 independent illustrative shocks: rate normal sigma 1%, spread normal sigma 50bp with -50bp floor, and equity log return normal mean -0.5×20%² and sigma20%. Yield floor guards are recorded. Scenarios reprice current cashflows; they do not roll the valuation date one year forward. Checks cover count, unique IDs, finite nonnegative values and per-scenario P&L reconciliation. No risk-neutral calibration, martingale test, market calibration, time-series dependence, real-world forecast, regulatory ESG adequacy or Rule19 compliance is claimed.

## Traceability and exclusions

Calculation records store input parameters, function/version, outputs, assumptions, check results and limitations. Only deterministic checks set complete/blocked status. The model omits liabilities, tax, operational/concentration/currency/default risk, rating-specific stresses, matching adjustment, hedges, statutory capital resources and prescribed floors/aggregation. Original formulas were written independently because upstream license grants could not be confirmed reliably.
