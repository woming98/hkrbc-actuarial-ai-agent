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

## Risk-module movement allocation

Closing date must be later than opening date. Recalculate both dates from their own holdings, cashflows, market values, yields and spreads. For each of six possible module replacement orders, replace opening modules by closing modules and record marginal aggregate changes. Their mean is exact three-player Shapley attribution:

```text
Σ attribution_i = aggregate_closing − aggregate_opening
unexplained_residual = actual_movement − Σ attribution_i
```

This reconciles nonlinear diversification without summing standalone module changes. Raw changes, diversification-benefit movement, new/removed asset IDs and exposure totals remain visible. This first allocation groups change by **risk module**; it does not isolate exposure, yield, ageing or mix. Its allocations depend on the specified aggregation and counterfactual module vectors. The separate input-factor bridge below answers a different question and is retained alongside the module allocation.

Reconciliation tolerance is HKD0.01 (relative tolerance 1e−10). A movement above HKD100,000 **and** above 50% of opening capital triggers an unresolved actuarial-review check and blocks completion, even when it reconciles. A material increase from zero also blocks completion. Thresholds are demonstration choices, with no reviewer override implemented.

## Date-first input-factor bridge

The service also attaches `factor_bridge`, implemented by `attribution.attribute_movement`. It revalues the opening positions at the closing date, keeping opening yields, spreads, bond face amounts and equity/cash values fixed. That explicitly chosen first leg is `date_ageing`. At the common closing date, an exact three-factor Shapley game then replaces:

| Factor | Input replacement |
|---|---|
| `holdings_and_equity_value` | Bond face amounts, position entry/exit, and observed equity/cash market values |
| `risk_free_yield` | Each matched bond's scalar annual-effective risk-free yield |
| `credit_spread` | Each matched bond's credit spread in basis points |

All eight factor coalitions and six replacement orders are calculated using the same nonlinear capital engine. Every state, ordered marginal leg, input fingerprint and validation is recorded. The bridge checks, using absolute HKD0.01 tolerance:

```text
date_ageing = capital(aged_opening_at_closing_date) − capital(opening)
Σ factor_allocation = capital(closing) − capital(aged_opening_at_closing_date)
date_ageing + Σ factor_allocation = capital(closing) − capital(opening)
```

Date ageing is a sequential first leg; its interactions follow that ordering. This is not a four-factor order-independent Shapley game. Within the subsequent common-date three-factor game, all six orders receive equal weight. Displaying each contribution to cents can introduce a small presentation-rounding difference; no residual plug is applied.

Matched IDs must retain asset type and currency; matched bonds must also retain coupon rate and maturity. A change to those terms blocks composition mapping. Entering bonds keep their sole observed closing quote in all states where held; departing bonds keep their sole opening quote. Missing-endpoint quotes are not invented, so entry/exit effects belong to holdings/composition. Equity/cash value changes jointly represent quantities, prices and flows because the snapshots contain no units, prices or transaction ledger. The bridge does not identify trades or reconstruct investment returns.

Positive scheduled coupon or principal payments in `(opening date, closing date]` block the bridge under the service's default `cashflow_policy="block"`. A position snapshot does not establish what happened to proceeds. Blocked output includes the event ledger, while its date leg, explained movement and residual remain `None`. Failure of this bridge blocks the combined analysis and marks any saved review report as blocked, even if the risk-module allocation reconciles.

An explicit advanced library call may instead choose `cashflow_policy="cash_no_interest"`: opening scheduled payments are assumed received in full into separate synthetic HKD cash, held without interest until closing; matured positions leave the aged book. This is a recorded **hypothetical path**, with no default, fees, tax or reinvestment. It does not establish actual receipt, returns or insurer behavior. The service/UI initially uses only the blocking policy.

See [movement-attribution.md](movement-attribution.md) for the exact hybrid definitions, coalition formula, output schema and cashflow boundary conventions.

## Independent numerical references

[actuarial_reference_cases.json](../evaluation/actuarial_reference_cases.json) records analytical definitions rather than snapshots produced by the tested engine. [test_attribution.py](../tests/test_attribution.py) verifies 50-digit Decimal zero-coupon PV and DV01; explicit coupon cashflows; first and second yield derivatives at several bump sizes; central-difference convergence; a zero-coupon closed-form date-capital bridge; and Shapley efficiency, symmetry, dummy-factor, relabeling, reversal and scaling identities. An independent subset-weight formula checks the recorded common-date coalition values.

Boundary tests cover coupon dates, maturity, entry/exit quote anchoring, same-ID instrument changes and explicit settlement cash. Service integration tests verify that unsupported attribution cannot produce a completed analysis or report. These are narrow model-verification checks. They do not validate HK RBC factors, legal currency, observed market data, transaction causality or production suitability.

## Scenario demonstration

A local seeded Python `random.Random` generates 1–1,000 independent illustrative shocks: rate normal sigma 1%, spread normal sigma 50bp with -50bp floor, and equity log return normal mean -0.5×20%² and sigma20%. Yield floor guards are recorded. Scenarios reprice current cashflows; they do not roll the valuation date one year forward. Checks cover count, unique IDs, finite nonnegative values and per-scenario P&L reconciliation. No risk-neutral calibration, martingale test, market calibration, time-series dependence, real-world forecast, regulatory ESG adequacy or Rule19 compliance is claimed.

## Traceability and exclusions

Calculation records store input parameters, function/version, outputs, assumptions, check results and limitations. Risk-module and input-factor allocations retain distinct component identifiers; the service records the combined analysis version and identity. Only deterministic checks set complete/blocked status. A saved blocked report is a review artifact, not a completed actuarial conclusion. The model omits liabilities, tax, operational/concentration/currency/default risk, rating-specific stresses, matching adjustment, hedges, statutory capital resources and prescribed floors/aggregation. Original formulas were written independently because upstream license grants could not be confirmed reliably.
