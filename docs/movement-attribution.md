# Counterfactual capital movement attribution

This bridge explains changes in the prototype's **illustrative diversified asset capital** through explicitly defined input replacements. It does not calculate statutory HK RBC capital, reconstruct trades, measure investment return, or establish economic causality. The original three-risk-module Shapley allocation remains useful and separate: a risk-module allocation answers a different question from a holdings/yield/spread input bridge.

## Bridge definition

Let `K(P, t)` mean the existing deterministic portfolio calculation, including its illustrative stress functions and nonlinear `sqrt(cᵀRc)` aggregation.

1. Calculate opening capital `K₀` from the opening portfolio at `t₀`.
2. Age the opening positions to closing date `t₁`, retaining opening risk-free yields, credit spreads, face amounts and equity/cash values. This produces `K_age` under the explicit cashflow policy below.
3. At `t₁`, replace three input groups between the aged opening book and the closing book. Evaluate all eight combinations and average marginal changes over all six orders.
4. Reconcile against actual closing capital `K₁` from the same existing engine.

The sequential date leg is:

```text
date_ageing = K_age - K₀
```

At the common closing date, the factors are:

| API key | Replacement | Meaning and limit |
| --- | --- | --- |
| `holdings_and_equity_value` | Bond face amounts, position entry/exit, and observed equity/cash market values | A joint holdings/composition/value change. Equity units, prices and cash flows are not available, so their effects are not separately inferred. |
| `risk_free_yield` | Scalar risk-free yield for each matched bond | A model input change at fixed remaining cashflow dates, with no yield-curve or transaction-timing inference. |
| `credit_spread` | Spread in basis points for each matched bond | A scalar spread-input change. It does not distinguish liquidity, default, migration or other economic causes. |

For a coalition `S` of factor replacements, `v(S)` is the engine's diversified capital for that hybrid portfolio. The exact allocation for factor `i` is:

```text
φᵢ = Σ [ |S|! (3-|S|-1)! / 3! ] × [v(S∪{i}) - v(S)]
      S ⊆ factors excluding i
```

The implementation independently enumerates the equivalent six orderings, records every marginal leg, and validates:

```text
v(empty) = K_age
v(all)   = K₁
Σ φᵢ     = K₁ - K_age
date_ageing + Σ φᵢ = K₁ - K₀
```

Each identity must reconcile within HKD0.01. The output preserves unrounded values; presentation rounding can introduce a small displayed difference. There is no forced plug or residual allocation.

Date ageing is deliberately applied **first**. Its interactions with later input changes follow this chosen sequence. It is not presented as a four-factor order-independent Shapley allocation. Within the subsequent three-factor common-date game, all six orders receive equal weight.

## Instrument identity and changing positions

Matched IDs must retain asset type and currency. Matched bonds must also retain coupon rate and maturity date. Changing those instrument terms under the same ID produces a structured blocked result. The code does not silently map a changed bond into a supposed yield or exposure movement.

An entering bond has only a closing quote. Its closing risk-free yield and spread are used in every state in which it is held. A departing bond analogously retains its opening quote. There is no invented missing-endpoint quote. Consequently, entry/exit effects are assigned to the holdings/composition factor, and market-factor contributions apply to matched instruments. This convention should be considered before comparing attribution across changing portfolios.

Equity and cash values follow the holdings/value factor. A cash change has zero capital effect under this particular asset model; it is still retained in the synthetic counterfactual inputs. This does not imply cash movements or liability financing are economically immaterial.

## Coupon crossings and maturities

The annual cashflow dates come from the existing maturity-anniversary schedule. Positive cashflows in `(opening date, closing date]` are recorded with asset ID, payment date, event type and amount. A payment on the opening date is excluded; one on the closing date is included. The maturity event contains principal plus the final full coupon, once.

The public integration defaults to `cashflow_policy="block"`. A crossed positive coupon or maturity payment blocks the factor bridge because two holdings snapshots do not establish whether proceeds were received, spent, reinvested or transferred. The blocked result preserves the valid opening-to-closing capital change and the event ledger, while `date_ageing`, explained movement and residual remain `None`. It must not be marked complete.

An advanced explicit call may select `cashflow_policy="cash_no_interest"`. This defines a **hypothetical** path:

- Scheduled opening-position coupons and principal are received in full into a separate synthetic HKD cash position.
- Cash earns no interest through closing. There is no default, tax, fee, reinvestment or transaction assumption beyond that explicitly chosen convention.
- Matured bonds leave the aged opening book; a book in which every bond matures can therefore age into cash only.
- The settlement cash ID is reserved against both actual portfolios, so it cannot silently collide with a real instrument.
- Closing holdings then replace this hypothetical aged book in the same common-date factor game.

The exact scheduled cash amounts and the resulting aged portfolio are recorded. Even when this optional path reconciles arithmetically, it does not establish what an insurer actually earned or did with the proceeds. The application initially exposes only the default blocking policy.

## API and validation

```python
from hkrbc_agent.attribution import attribute_movement, attribute_same_date

bridge = attribute_movement(opening, closing)  # closing date must be later
same_date = attribute_same_date(book_a, book_b)  # identical valuation date
```

`attribute_movement` accepts `materiality_hkd` and `unexpected_movement_ratio`, matching the original comparison's review controls. A large movement that requires review still blocks completion even if all arithmetic reconciles. The common-date helper checks portfolio and structural validity without imposing a chronological review threshold.

Important fields are:

| Field | Meaning |
| --- | --- |
| `status` | `complete` only when all deterministic checks pass; otherwise `blocked` |
| `date_ageing` | HKD sequential date leg; `None` when unsupported |
| `factor_attribution` | Three common-date HKD allocations; empty when unsupported |
| `total_movement` | Existing closing aggregate capital minus opening aggregate capital |
| `explained_movement` | Date leg plus three allocations, or `None` when unsupported |
| `unexplained_residual` | Actual less explained movement, or `None` when unsupported |
| `states` | Eight coalition capital values, module capitals, fingerprints and validation status |
| `permutations` | Six full ordered bridges, each with three explicit marginal legs |
| `cashflow_events` | Scheduled payments that intersect the date interval |
| `composition_conflicts` | Same-ID changes that prevent a defensible instrument mapping |
| `calculations` | Input portfolios, hybrid definitions, function/engine versions, outputs, checks, assumptions and limitations |

Malformed original data or invalid API parameters raise `ValidationError`. Economically unsupported identity mappings and default-policy cashflow crossings return structured blocked results. Any invalid required counterfactual also blocks completion; the code does not skip a difficult state or average fewer orderings.

## Independent verification

`evaluation/actuarial_reference_cases.json` documents analytical reference definitions. `tests/test_attribution.py` uses:

- Direct 50-digit Decimal zero-coupon PV and DV01, with the expected derivative formulas.
- First and second finite differences at multiple bump sizes; the first-derivative central-difference error converges quadratically before floating-point limits.
- Explicit three-payment coupon-bond discounting, independent of the implementation's cashflow generator.
- A zero-coupon date-ageing capital identity: rate and spread stresses both add one percent to yield, so their combined two-module capital equals `sqrt(2.5)` times the standalone loss under the prototype's illustrative correlation.
- Additive cooperative games, symmetric interaction splitting, dummy factors, factor relabeling, reversal and exposure scaling.
- The independent subset-weight formula applied to recorded state values.
- Entry/exit quote conventions, instrument changes, coupon boundary dates, maturity settlement and cash-ID collision controls.
- Reconciliation to the existing sample comparison and every recorded permutation.

These checks verify a narrow numerical model and explicit conventions. They do not validate regulatory calibration, current law, market data, causal explanations or enterprise production use.
