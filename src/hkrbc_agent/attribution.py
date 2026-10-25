"""Explicit counterfactual capital bridges, not reconstructed transaction returns.

The opening book first ages at opening quotes. At the closing date, exact
Shapley attribution averages all six orders of three well-defined factor
replacements. Unsupported instrument remapping or unknown cashflow treatment
blocks completion. All underlying capital remains illustrative.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import replace
from datetime import date, timedelta
from typing import Any, Mapping

from .calculations import (
    FUNCTION_VERSION as ENGINE_VERSION,
    LIMITATIONS as ENGINE_LIMITATIONS,
    MODEL_LABEL,
    analyse_portfolio,
    bond_cashflows,
    compare_portfolios,
    validate_portfolio_prices,
)
from .portfolio import Asset, Portfolio, ValidationError, finite_number


FUNCTION_VERSION = "1.0.0"
FACTORS = ("holdings_and_equity_value", "risk_free_yield", "credit_spread")
LIMITATIONS = list(ENGINE_LIMITATIONS) + [
    "Counterfactual model attribution is not a transaction ledger, investment return, or proof of economic causality.",
    "Date ageing is applied first at opening bond quotes; its interactions with market/holding changes are allocated by that explicit ordering.",
    "Equity/cash market-value changes jointly represent quantities, prices and flows; units and trade data are unavailable, so these causes cannot be separated.",
    "Entry/exit bonds have only one observed endpoint quote; that quote is held fixed in all counterfactual states and their effect is assigned to holdings/composition.",
    "Same-ID changes of asset type, coupon or maturity are blocked. Use distinct IDs for genuinely different instruments, with supporting trade evidence outside this prototype.",
    "A flat scalar risk-free yield and scalar credit spread are independent input factors; no observed yield-curve, liquidity/default decomposition or official HK RBC calibration is implied.",
]


def _sum(values: Any) -> float:
    try:
        value = math.fsum(values)
    except (OverflowError, ValueError) as exc:
        raise ValidationError("attribution sum is not finite") from exc
    return finite_number(value, "attribution sum")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _check(name: str, passed: bool, details: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "severity": "error", "details": details}


def _subsets(factors: tuple[str, ...] = FACTORS) -> tuple[frozenset[str], ...]:
    return tuple(frozenset(subset) for size in range(len(factors) + 1)
                 for subset in itertools.combinations(factors, size))


def exact_shapley(game_values: Mapping[frozenset[str], float], *,
                  factors: tuple[str, str, str] = FACTORS) -> dict[str, float]:
    """Average exact marginal changes over all six factor permutations.

    Values for all eight coalitions must be supplied. The function is also
    exposed for independent cooperative-game identities; no pricing is done.
    """
    if (not isinstance(factors, tuple) or len(factors) != 3 or
            any(not isinstance(name, str) or not name for name in factors) or len(set(factors)) != 3):
        raise ValidationError("exact_shapley requires three unique factor names")
    if not isinstance(game_values, Mapping) or set(game_values) != set(_subsets(factors)):
        raise ValidationError("exact_shapley requires exactly all eight factor coalitions")
    checked = {coalition: finite_number(value, "coalition value") for coalition, value in game_values.items()}
    marginal: dict[str, list[float]] = {factor: [] for factor in factors}
    for ordering in itertools.permutations(factors):
        coalition: frozenset[str] = frozenset()
        for factor in ordering:
            next_coalition = coalition | {factor}
            marginal[factor].append((checked[next_coalition] - checked[coalition]) / 6)
            coalition = next_coalition
    return {factor: _sum(marginal[factor]) for factor in factors}


def _instrument_conflicts(opening: Portfolio, closing: Portfolio) -> list[dict[str, Any]]:
    before = {asset.asset_id: asset for asset in opening.assets}
    after = {asset.asset_id: asset for asset in closing.assets}
    conflicts = []
    for asset_id in sorted(before.keys() & after.keys()):
        start, end = before[asset_id], after[asset_id]
        fields = ("asset_type", "currency")
        if start.asset_type == end.asset_type == "bond":
            fields += ("coupon_rate", "maturity_date")
        changed = [field for field in fields if getattr(start, field) != getattr(end, field)]
        if changed:
            conflicts.append({"asset_id": asset_id, "changed_instrument_fields": changed})
    return conflicts


def _events(opening: Portfolio, closing_date: date) -> list[dict[str, Any]]:
    events = []
    for asset in sorted(opening.assets, key=lambda item: item.asset_id):
        if asset.asset_type != "bond":
            continue
        for time, amount in bond_cashflows(asset):
            payment_date = asset.valuation_date + timedelta(days=round(time * 365.25))
            if asset.valuation_date < payment_date <= closing_date and amount > 0:
                events.append({"asset_id": asset.asset_id, "payment_date": payment_date.isoformat(),
                               "event_type": "maturity" if payment_date == asset.maturity_date else "coupon",
                               "amount_hkd": amount})
    return sorted(events, key=lambda item: (item["payment_date"], item["asset_id"]))


def _age(opening: Portfolio, closing_date: date, events: list[dict[str, Any]],
         cashflow_policy: str, closing_ids: set[str]) -> tuple[Portfolio, str | None]:
    assets = []
    for asset in opening.assets:
        if asset.asset_type == "bond" and asset.maturity_date <= closing_date:
            continue
        assets.append(replace(asset, valuation_date=closing_date,
                              market_value=None if asset.asset_type == "bond" else asset.market_value))
    settlement_id = None
    if events and cashflow_policy == "cash_no_interest":
        used = {asset.asset_id for asset in opening.assets} | closing_ids
        settlement_id = "SYN-ATTR-SETTLEMENT"
        suffix = 0
        while settlement_id in used:
            suffix += 1
            settlement_id = f"SYN-ATTR-SETTLEMENT-{suffix}"
        assets.append(Asset(settlement_id, "cash", "HKD", closing_date, _sum(event["amount_hkd"] for event in events)))
    return Portfolio(tuple(assets), closing_date), settlement_id


def _hybrid(opening: Portfolio, closing: Portfolio, active: frozenset[str]) -> Portfolio:
    """Common-date book with explicit quote conventions for unmatched assets."""
    before = {asset.asset_id: asset for asset in opening.assets}
    after = {asset.asset_id: asset for asset in closing.assets}
    use_closing_holdings = "holdings_and_equity_value" in active
    assets = []
    for asset_id in sorted(before.keys() | after.keys()):
        start, end = before.get(asset_id), after.get(asset_id)
        held = end if use_closing_holdings else start
        if held is None:
            continue
        if held.asset_type != "bond":
            assets.append(held)
            continue
        # Matched instruments can replace market factors independently. Entry
        # or exit instruments retain their sole observed quote in both states.
        rate_source = (end if "risk_free_yield" in active else start) if start and end else held
        spread_source = (end if "credit_spread" in active else start) if start and end else held
        assets.append(replace(held, market_value=None, yield_rate=rate_source.yield_rate,
                              credit_spread_bps=spread_source.credit_spread_bps))
    return Portfolio(tuple(assets), closing.valuation_date)


def _record(function: str, inputs: dict[str, Any], outputs: dict[str, Any],
            checks: list[dict[str, Any]], assumptions: list[str]) -> dict[str, Any]:
    return {"function": function, "version": FUNCTION_VERSION, "engine_version": ENGINE_VERSION,
            "inputs": inputs, "outputs": outputs, "assumptions": assumptions,
            "validation": {"passed": all(check["passed"] for check in checks), "checks": checks},
            "limitations": list(LIMITATIONS)}


def _same_date_states(opening: Portfolio, closing: Portfolio) -> tuple[list[dict[str, Any]], dict[str, float], list[dict[str, Any]], list[dict[str, Any]]]:
    states = []
    game: dict[frozenset[str], float] = {}
    records = []
    for active in _subsets():
        hybrid = _hybrid(opening, closing, active)
        analysis = analyse_portfolio(hybrid)
        capital = analysis["aggregate_capital"]
        game[active] = capital
        state = {"active_factors": sorted(active), "aggregate_capital": capital,
                 "module_capital": analysis["module_capital"], "market_value": analysis["total_market_value"],
                 "input_fingerprint": analysis["input_fingerprint"], "validation_passed": analysis["validation"]["passed"]}
        states.append(state)
        records.append(_record("factor_hybrid_capital", {"active_factors": sorted(active), "portfolio": hybrid.to_dict()},
                               state, analysis["validation"]["checks"],
                               ["All positions use the common closing valuation date.",
                                "Matched bond face amount follows holdings; risk-free yield and spread follow independent factor flags.",
                                "Entry/exit bonds keep their sole observed quote; equity/cash value changes are joint holdings/market changes."]))
    attribution = exact_shapley(game)
    permutations = []
    for ordering in itertools.permutations(FACTORS):
        active: frozenset[str] = frozenset()
        legs = []
        for factor in ordering:
            next_active = active | {factor}
            legs.append({"factor": factor, "opening_capital": game[active], "closing_capital": game[next_active],
                         "movement": game[next_active] - game[active]})
            active = next_active
        permutations.append({"ordering": list(ordering), "legs": legs,
                             "total_movement": _sum(leg["movement"] for leg in legs)})
    return states, attribution, permutations, records


def _base_result(opening: Portfolio, closing: Portfolio, start: dict[str, Any], end: dict[str, Any], *, cashflow_policy: str) -> dict[str, Any]:
    before = {asset.asset_id for asset in opening.assets}
    after = {asset.asset_id for asset in closing.assets}
    closing_by_id = {asset.asset_id: asset for asset in closing.assets}
    return {"status": "blocked", "model_label": MODEL_LABEL, "function_version": FUNCTION_VERSION,
            "engine_version": ENGINE_VERSION, "currency": "HKD", "opening_date": opening.valuation_date.isoformat(),
            "closing_date": closing.valuation_date.isoformat(), "cashflow_policy": cashflow_policy,
            "opening_capital": start["aggregate_capital"], "closing_capital": end["aggregate_capital"],
            "total_movement": end["aggregate_capital"] - start["aggregate_capital"],
            "date_ageing": None, "same_date_movement": None, "factor_attribution": {},
            "explained_movement": None, "unexplained_residual": None, "states": [], "permutations": [],
            "cashflow_events": [], "settlement_cash_asset_id": None,
            "added_asset_ids": sorted(after - before), "removed_asset_ids": sorted(before - after),
            "matched_bond_ids": sorted(asset.asset_id for asset in opening.assets if asset.asset_type == "bond" and asset.asset_id in after
                                       and closing_by_id[asset.asset_id].asset_type == "bond"
                                       and asset.coupon_rate == closing_by_id[asset.asset_id].coupon_rate
                                       and asset.maturity_date == closing_by_id[asset.asset_id].maturity_date),
            "calculations": [], "limitations": list(LIMITATIONS),
            "input_fingerprints": {"opening": _fingerprint(opening.to_dict()), "closing": _fingerprint(closing.to_dict())}}


def _finish(result: dict[str, Any], checks: list[dict[str, Any]], opening: Portfolio, closing: Portfolio) -> dict[str, Any]:
    passed = all(check["passed"] for check in checks)
    result["validation"] = {"passed": passed, "checks": checks}
    result["status"] = "complete" if passed else "blocked"
    result["calculations"].append(_record("attribute_capital_movement", {"opening": opening.to_dict(), "closing": closing.to_dict(),
                                  "cashflow_policy": result["cashflow_policy"], "factor_order": list(FACTORS)},
                                  {key: result[key] for key in ("total_movement", "date_ageing", "same_date_movement", "factor_attribution", "explained_movement", "unexplained_residual")}, checks,
                                  ["Date ageing is a sequential first leg, followed by exact Shapley at one date.",
                                   "No historical transaction or investment-return causality is inferred."]))
    result["report_id"] = "attribution-" + _fingerprint(result)[:16]
    return result


def attribute_same_date(opening: Portfolio, closing: Portfolio) -> dict[str, Any]:
    """Exact common-date factor attribution; structural conflicts return blocked."""
    validate_portfolio_prices(opening)
    validate_portfolio_prices(closing)
    if opening.valuation_date != closing.valuation_date:
        raise ValidationError("attribute_same_date requires the same valuation_date")
    start, end = analyse_portfolio(opening), analyse_portfolio(closing)
    result = _base_result(opening, closing, start, end, cashflow_policy="not_applicable")
    conflicts = _instrument_conflicts(opening, closing)
    result["composition_conflicts"] = conflicts
    checks = [_check("portfolio_validation", start["validation"]["passed"] and end["validation"]["passed"], "Both original portfolio validations pass."),
              _check("instrument_identity", not conflicts, "Matched IDs must keep asset type, currency, bond coupon and maturity.")]
    if conflicts:
        return _finish(result, checks, opening, closing)
    return _complete_states(result, checks, opening, closing, opening, start, end)


def _complete_states(result: dict[str, Any], checks: list[dict[str, Any]], opening: Portfolio,
                     closing: Portfolio, aged: Portfolio, start: dict[str, Any], end: dict[str, Any]) -> dict[str, Any]:
    try:
        aged_analysis = analyse_portfolio(aged)
        states, factors, permutations, records = _same_date_states(aged, closing)
    except ValidationError as exc:
        checks.append(_check("counterfactual_validity", False, "A required hybrid cannot be valued: " + str(exc)))
        return _finish(result, checks, opening, closing)
    zero = next(state for state in states if not state["active_factors"])
    full = next(state for state in states if len(state["active_factors"]) == 3)
    date_leg = aged_analysis["aggregate_capital"] - start["aggregate_capital"]
    same_date = end["aggregate_capital"] - aged_analysis["aggregate_capital"]
    factor_sum = _sum(factors.values())
    explained = _sum((date_leg, factor_sum))
    residual = result["total_movement"] - explained
    checks += [
        _check("aged_portfolio_validation", aged_analysis["validation"]["passed"], "Opening holdings at closing date satisfy deterministic valuation checks."),
        _check("all_hybrid_validations", all(state["validation_passed"] for state in states), "All eight required counterfactual portfolios pass deterministic validation."),
        _check("hybrid_endpoints", math.isclose(zero["aggregate_capital"], aged_analysis["aggregate_capital"], abs_tol=0.01, rel_tol=0) and
               math.isclose(full["aggregate_capital"], end["aggregate_capital"], abs_tol=0.01, rel_tol=0), "Empty/full factor coalitions reproduce aged-opening/closing capital within HKD0.01."),
        _check("same_date_shapley_reconciliation", math.isclose(factor_sum, same_date, abs_tol=0.01, rel_tol=0), "Three factor attributions sum to the same-date diversified capital change within HKD0.01."),
        _check("every_permutation_reconciliation", all(math.isclose(item["total_movement"], same_date, abs_tol=0.01, rel_tol=0) for item in permutations), "Each of six ordered bridges telescopes to the same-date change within HKD0.01."),
        _check("full_bridge_reconciliation", math.isclose(residual, 0, abs_tol=0.01, rel_tol=0), "Date ageing plus exact factor attribution reconciles the original nonlinear aggregate capital movement within HKD0.01."),
    ]
    result.update(date_ageing=date_leg, same_date_movement=same_date, factor_attribution=factors,
                  explained_movement=explained, unexplained_residual=residual, states=states, permutations=permutations,
                  aged_opening_capital=aged_analysis["aggregate_capital"], aged_input_fingerprint=aged_analysis["input_fingerprint"])
    result["calculations"] += records
    result["calculations"].append(_record("age_opening_positions", {"opening": opening.to_dict(), "closing_date": closing.valuation_date.isoformat(),
                                  "cashflow_policy": result["cashflow_policy"], "cashflow_events": result["cashflow_events"], "aged_portfolio": aged.to_dict()},
                                  {"opening_capital": start["aggregate_capital"], "aged_opening_capital": aged_analysis["aggregate_capital"], "date_ageing": date_leg},
                                  [checks[-6]], ["Opening bond yields/spreads are held fixed; annual maturity-anniversary cashflows follow the existing engine.",
                                                 "Equity/cash market values stay fixed during date ageing.",
                                                 "Only under explicit cash_no_interest policy, scheduled positive receipts are held as separate HKD cash without interest; this is a hypothetical settlement path."]))
    return _finish(result, checks, opening, closing)


def attribute_movement(opening: Portfolio, closing: Portfolio, *, cashflow_policy: str = "block",
                       materiality_hkd: float = 100_000.0, unexpected_movement_ratio: float = 0.5) -> dict[str, Any]:
    """Date-first capital bridge plus common-date exact three-factor Shapley.

    Default policy blocks crossed positive coupons or maturity cashflows because
    a holdings snapshot cannot establish what happened to proceeds. Explicit
    cash_no_interest instead creates a clearly hypothetical settlement-cash path.
    This option does not infer what an insurer actually received or reinvested.
    """
    if cashflow_policy not in ("block", "cash_no_interest"):
        raise ValidationError("cashflow_policy must be block or cash_no_interest")
    comparison = compare_portfolios(opening, closing, materiality_hkd=materiality_hkd,
                                    unexpected_movement_ratio=unexpected_movement_ratio)
    start, end = comparison["opening"], comparison["closing"]
    result = _base_result(opening, closing, start, end, cashflow_policy=cashflow_policy)
    conflicts = _instrument_conflicts(opening, closing)
    events = _events(opening, closing.valuation_date)
    result.update(composition_conflicts=conflicts, cashflow_events=events)
    checks = [_check("original_comparison_validation", comparison["validation"]["passed"], "Original compare_portfolios validation, including unexpected-movement review, must pass."),
              _check("instrument_identity", not conflicts, "Matched IDs must keep asset type, currency, bond coupon and maturity."),
              _check("cashflow_bridge_supported", not events or cashflow_policy == "cash_no_interest",
                     "Default block policy rejects positive coupon or maturity events in (opening date, closing date]; explicit hypothetical cash settlement is required.")]
    if conflicts or (events and cashflow_policy == "block"):
        return _finish(result, checks, opening, closing)
    try:
        aged, settlement_id = _age(opening, closing.valuation_date, events, cashflow_policy,
                                   {asset.asset_id for asset in closing.assets})
    except ValidationError as exc:
        checks.append(_check("aged_portfolio_construction", False, str(exc)))
        return _finish(result, checks, opening, closing)
    result["settlement_cash_asset_id"] = settlement_id
    if cashflow_policy == "cash_no_interest":
        result["limitations"].append("Explicit hypothetical path: opening scheduled coupon/principal payments are received in full into separate HKD cash, held without interest until closing; no default, fees, tax or reinvestment is assumed. This is not reconstructed historical P&L.")
    return _complete_states(result, checks, opening, closing, aged, start, end)
