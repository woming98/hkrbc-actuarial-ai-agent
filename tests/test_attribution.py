"""Analytical reference checks and explicit counterfactual-bridge contracts."""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from hkrbc_agent.attribution import FACTORS, attribute_movement, attribute_same_date, exact_shapley
from hkrbc_agent.calculations import bond_metrics, bond_price, compare_portfolios
from hkrbc_agent.portfolio import Asset, Portfolio, ValidationError, load_portfolio_csv


ROOT = Path(__file__).resolve().parents[1]
DATE = date(2025, 1, 1)


def _bond(*, asset_id="SYN-BOND", when=DATE, face=1_000_000, coupon=0.0, risk_free=0.03,
          spread=100.0, maturity=date(2030, 1, 1)):
    return Asset(asset_id, "bond", "HKD", when, None, face, coupon, risk_free, maturity, spread)


def _portfolio(*assets):
    return Portfolio(tuple(assets), assets[0].valuation_date)


def _coalitions(factors):
    return [frozenset(items) for size in range(4) for items in itertools.combinations(factors, size)]


def _zero_capital(face, annual_yield, years):
    # Independent closed form for a zero-coupon book with no equity: rate and
    # credit stress losses coincide, so sqrt(c^T R c) = sqrt(2.5) * loss.
    return math.sqrt(2.5) * face * ((1 + annual_yield)**(-years) - (1 + annual_yield + 0.01)**(-years))


def test_high_precision_reference_cases_are_direct_analytical_arithmetic():
    reference = json.loads((ROOT / "evaluation" / "actuarial_reference_cases.json").read_text())
    zero = next(item for item in reference["references"] if item["case_id"] == "zero-coupon-four-year")
    with localcontext() as context:
        context.prec = 50
        face, annual_yield, years = Decimal(1_000_000), Decimal("0.05"), Decimal(4)
        expected_price = face / (1 + annual_yield)**4
        expected_dv01 = expected_price * years / (1 + annual_yield) * Decimal("0.0001")
        assert Decimal(zero["expected_decimal"]["price"]) == expected_price
        assert Decimal(zero["expected_decimal"]["dv01"]) == expected_dv01
        metrics = bond_metrics(1_000_000, 0, 0.05, 4)
        assert metrics["price"] == pytest.approx(float(expected_price), abs=1e-6)
        assert metrics["dv01"] == pytest.approx(float(expected_dv01), abs=1e-6)
        assert metrics["modified_duration"] == pytest.approx(float(years / (1 + annual_yield)), abs=1e-12)


def test_zero_coupon_first_and_second_derivatives_at_multiple_bump_sizes():
    face, annual_yield, years = 1_000_000, .05, 4
    with localcontext() as context:
        context.prec = 50
        f, y, t = Decimal(face), Decimal(".05"), Decimal(years)
        first_reference = float(-f * t / (1 + y)**5)
        second_reference = float(f * t * (t + 1) / (1 + y)**6)
    bumps = (.01, .001, .0001, .00001)
    errors = []
    for bump in bumps:
        upper = bond_price(face, 0, annual_yield + bump, years)
        lower = bond_price(face, 0, annual_yield - bump, years)
        center = bond_price(face, 0, annual_yield, years)
        derivative = (upper - lower) / (2 * bump)
        errors.append(abs(derivative - first_reference))
        if bump >= .0001:
            second = (upper - 2 * center + lower) / bump**2
            assert second == pytest.approx(second_reference, rel=0.001 if bump == .01 else 1e-5)
    assert all(errors[index + 1] < errors[index] for index in range(3))
    assert 90 < errors[0] / errors[1] < 110
    assert 90 < errors[1] / errors[2] < 110
    assert errors[-1] / abs(first_reference) < 1e-8


def test_coupon_reference_uses_explicit_cashflows_without_engine_schedule():
    with localcontext() as context:
        context.prec = 50
        discount = Decimal("1.05")
        values = [Decimal(4) / discount, Decimal(4) / discount**2, Decimal(104) / discount**3]
        pv = sum(values)
        weighted = sum(Decimal(index + 1) * value for index, value in enumerate(values))
        expected_duration = weighted / pv / discount
        expected_dv01 = weighted / discount * Decimal(".0001")
    actual = bond_metrics(100, .04, .05, 3)
    assert actual["price"] == pytest.approx(float(pv), abs=1e-12)
    assert actual["modified_duration"] == pytest.approx(float(expected_duration), abs=1e-12)
    assert actual["dv01"] == pytest.approx(float(expected_dv01), abs=1e-12)


def test_exact_shapley_additive_interactions_dummy_and_symmetric_games():
    factors = ("a", "b", "c")
    coalitions = _coalitions(factors)
    interaction = {items: 100 + 10 * ("a" in items) + 20 * ("b" in items) + 12 * ({"a", "b"} <= items)
                   for items in coalitions}
    assert exact_shapley(interaction, factors=factors) == {"a": 16, "b": 26, "c": 0}
    symmetric = {items: len(items)**2 for items in coalitions}
    assert exact_shapley(symmetric, factors=factors) == {"a": 3, "b": 3, "c": 3}
    assert exact_shapley(interaction, factors=("c", "b", "a")) == {"a": 16, "b": 26, "c": 0}


def test_shapley_all_eight_coalitions_required_and_finite_nonboolean():
    game = {items: float(len(items)) for items in _coalitions(FACTORS)}
    missing = dict(game)
    missing.pop(frozenset())
    for invalid in (missing, {**game, frozenset(): True}, {**game, frozenset(): float("nan")}):
        with pytest.raises(ValidationError):
            exact_shapley(invalid)
    with pytest.raises(ValidationError):
        exact_shapley(game, factors=("a", "a", "c"))


def test_zero_coupon_ageing_leg_matches_independent_closed_form():
    opening_asset = _bond()
    closing_date = date(2025, 7, 1)
    opening = _portfolio(opening_asset)
    closing = _portfolio(replace(opening_asset, valuation_date=closing_date))
    bridge = attribute_movement(opening, closing)
    t0 = (opening_asset.maturity_date - DATE).days / 365.25
    t1 = (opening_asset.maturity_date - closing_date).days / 365.25
    expected = _zero_capital(1_000_000, .04, t1) - _zero_capital(1_000_000, .04, t0)
    assert bridge["status"] == "complete"
    assert bridge["date_ageing"] == pytest.approx(expected, abs=1e-8)
    assert all(value == 0 for value in bridge["factor_attribution"].values())
    assert bridge["unexplained_residual"] == pytest.approx(0, abs=.01)


def test_pure_exposure_scale_has_closed_form_and_market_factors_are_dummy():
    opening_asset = _bond()
    result = attribute_same_date(_portfolio(opening_asset), _portfolio(replace(opening_asset, face_value=2_000_000)))
    years = (opening_asset.maturity_date - DATE).days / 365.25
    expected = _zero_capital(1_000_000, .04, years)
    assert result["factor_attribution"]["holdings_and_equity_value"] == pytest.approx(expected, abs=1e-8)
    assert result["factor_attribution"]["risk_free_yield"] == result["factor_attribution"]["credit_spread"] == 0
    assert result["date_ageing"] == 0


def test_equal_yield_and_spread_changes_are_symmetric_and_holdings_dummy():
    asset = _bond()
    result = attribute_same_date(_portfolio(asset), _portfolio(replace(asset, yield_rate=.035, credit_spread_bps=150)))
    factors = result["factor_attribution"]
    assert factors["holdings_and_equity_value"] == 0
    assert factors["risk_free_yield"] == pytest.approx(factors["credit_spread"], abs=1e-8)
    assert sum(factors.values()) == pytest.approx(result["total_movement"], abs=1e-8)


def test_full_sample_bridge_matches_existing_nonlinear_comparison_and_each_order():
    opening, closing = (load_portfolio_csv(ROOT / "data" / "portfolios" / name) for name in ("opening.csv", "closing.csv"))
    result = attribute_movement(opening, closing)
    existing = compare_portfolios(opening, closing)
    assert result["status"] == "complete" and result["validation"]["passed"]
    assert result["total_movement"] == existing["capital_movement"]
    assert result["date_ageing"] + sum(result["factor_attribution"].values()) == pytest.approx(existing["capital_movement"], abs=.01)
    assert len(result["states"]) == 8 and len(result["permutations"]) == 6
    for ordering in result["permutations"]:
        assert sum(leg["movement"] for leg in ordering["legs"]) == pytest.approx(result["same_date_movement"], abs=.01)
        assert ordering["legs"][0]["opening_capital"] == result["aged_opening_capital"]
        assert ordering["legs"][-1]["closing_capital"] == result["closing_capital"]
    assert json.dumps(result, allow_nan=False)
    assert attribute_movement(opening, closing) == result
    for record in result["calculations"]:
        assert record["version"] == "1.0.0"
        assert all(key in record for key in ("inputs", "outputs", "assumptions", "validation", "limitations"))


def test_factor_attribution_agrees_with_independent_subset_weight_formula():
    asset = _bond(coupon=.04)
    result = attribute_same_date(_portfolio(asset), _portfolio(replace(asset, face_value=1_300_000, yield_rate=.025, credit_spread_bps=150)))
    game = {frozenset(state["active_factors"]): state["aggregate_capital"] for state in result["states"]}
    for factor in FACTORS:
        others = tuple(name for name in FACTORS if name != factor)
        reference = 0.0
        for size in range(3):
            for members in itertools.combinations(others, size):
                coalition = frozenset(members)
                weight = math.factorial(size) * math.factorial(2 - size) / math.factorial(3)
                reference += weight * (game[coalition | {factor}] - game[coalition])
        assert result["factor_attribution"][factor] == pytest.approx(reference, abs=1e-8)


def test_common_date_reversal_and_scale_invariance():
    asset = _bond(coupon=.04)
    start, end = _portfolio(asset), _portfolio(replace(asset, face_value=1_200_000, yield_rate=.025, credit_spread_bps=175))
    forward, reverse = attribute_same_date(start, end), attribute_same_date(end, start)
    scaled = attribute_same_date(_portfolio(replace(asset, face_value=2_000_000)),
                                 _portfolio(replace(end.assets[0], face_value=2_400_000)))
    for factor in FACTORS:
        assert forward["factor_attribution"][factor] == pytest.approx(-reverse["factor_attribution"][factor], abs=1e-8)
        assert scaled["factor_attribution"][factor] == pytest.approx(2 * forward["factor_attribution"][factor], abs=1e-8)


def test_entry_exit_quotes_are_not_invented_and_only_composition_changes():
    start = _portfolio(_bond(asset_id="SYN-EXIT", risk_free=.02, spread=25))
    end = _portfolio(_bond(asset_id="SYN-ENTRY", risk_free=.07, spread=500, maturity=date(2035, 1, 1)))
    result = attribute_same_date(start, end)
    assert result["status"] == "complete"
    assert result["factor_attribution"]["risk_free_yield"] == result["factor_attribution"]["credit_spread"] == 0
    assert result["factor_attribution"]["holdings_and_equity_value"] == pytest.approx(result["total_movement"])
    for record in result["calculations"]:
        if record["function"] == "factor_hybrid_capital":
            asset = record["inputs"]["portfolio"]["assets"][0]
            if asset["asset_id"] == "SYN-EXIT":
                assert asset["yield_rate"] == .02 and asset["credit_spread_bps"] == 25
            else:
                assert asset["yield_rate"] == .07 and asset["credit_spread_bps"] == 500


def test_equity_joint_market_value_and_cash_changes_have_no_fake_price_flow_split():
    equity = Asset("SYN-EQ", "equity", "HKD", DATE, 1_000_000)
    cash = Asset("SYN-CASH", "cash", "HKD", DATE, 10_000_000)
    result = attribute_same_date(_portfolio(equity, cash), _portfolio(replace(equity, market_value=1_500_000), replace(cash, market_value=1)))
    assert result["factor_attribution"] == {"holdings_and_equity_value": 150_000, "risk_free_yield": 0, "credit_spread": 0}
    assert any("quantities, prices and flows" in text for text in result["limitations"])


@pytest.mark.parametrize("changed", [{"coupon_rate": .05}, {"maturity_date": date(2031, 1, 1)}])
def test_changed_matched_bond_terms_block_composition_mapping(changed):
    asset = _bond(coupon=.04)
    result = attribute_same_date(_portfolio(asset), _portfolio(replace(asset, **changed)))
    assert result["status"] == "blocked" and not result["validation"]["passed"]
    assert result["composition_conflicts"][0]["changed_instrument_fields"] == list(changed)
    assert result["factor_attribution"] == {} and result["unexplained_residual"] is None


def test_changed_asset_type_blocks_even_if_total_capital_computes():
    opening = _portfolio(_bond())
    closing = _portfolio(Asset("SYN-BOND", "equity", "HKD", date(2025, 7, 1), 1_000_000))
    result = attribute_movement(opening, closing)
    assert result["status"] == "blocked" and result["date_ageing"] is None
    assert result["composition_conflicts"] == [{"asset_id": "SYN-BOND", "changed_instrument_fields": ["asset_type"]}]


def test_coupon_crossing_is_structured_block_by_default():
    asset = _bond(coupon=.04, maturity=date(2030, 6, 30))
    closing_asset = replace(asset, valuation_date=date(2025, 8, 1))
    result = attribute_movement(_portfolio(asset), _portfolio(closing_asset))
    assert result["status"] == "blocked"
    assert result["cashflow_events"] == [{"asset_id": "SYN-BOND", "payment_date": "2025-06-30", "event_type": "coupon", "amount_hkd": 40_000}]
    assert result["explained_movement"] is result["unexplained_residual"] is result["date_ageing"] is None
    assert any(check["name"] == "cashflow_bridge_supported" and not check["passed"] for check in result["validation"]["checks"])


def test_explicit_coupon_cash_path_has_auditable_full_payments_and_no_interest():
    asset = _bond(face=100_000, coupon=.04, maturity=date(2030, 6, 30))
    closing_asset = replace(asset, valuation_date=date(2027, 8, 1))
    result = attribute_movement(_portfolio(asset), _portfolio(closing_asset), cashflow_policy="cash_no_interest")
    assert result["status"] == "complete"
    assert [event["payment_date"] for event in result["cashflow_events"]] == ["2025-06-30", "2026-06-30", "2027-06-30"]
    age = next(record for record in result["calculations"] if record["function"] == "age_opening_positions")
    cash = next(row for row in age["inputs"]["aged_portfolio"]["assets"] if row["asset_type"] == "cash")
    assert cash["market_value"] == 12_000
    assert cash["asset_id"] == result["settlement_cash_asset_id"]
    assert all(value == 0 for value in result["factor_attribution"].values())
    assert any("without interest" in text and "hypothetical" in text for text in result["limitations"])


def test_payment_on_opening_date_excluded_and_on_closing_date_included():
    asset = _bond(when=date(2025, 6, 30), coupon=.04, maturity=date(2030, 6, 30))
    result = attribute_movement(_portfolio(asset), _portfolio(replace(asset, valuation_date=date(2026, 6, 30))))
    assert len(result["cashflow_events"]) == 1
    assert result["cashflow_events"][0]["payment_date"] == "2026-06-30"


def test_maturity_defaults_block_but_explicit_settlement_can_age_to_cash_only():
    asset = _bond(face=100_000, coupon=.04, maturity=date(2025, 6, 30))
    closing = _portfolio(Asset("SYN-CASH", "cash", "HKD", date(2025, 8, 1), 104_000))
    blocked = attribute_movement(_portfolio(asset), closing)
    assert blocked["status"] == "blocked"
    assert blocked["cashflow_events"][0]["event_type"] == "maturity"
    assert blocked["cashflow_events"][0]["amount_hkd"] == 104_000
    settled = attribute_movement(_portfolio(asset), closing, cashflow_policy="cash_no_interest")
    assert settled["status"] == "complete"
    assert settled["aged_opening_capital"] == 0
    assert settled["date_ageing"] == -settled["opening_capital"]
    assert settled["total_movement"] == settled["date_ageing"]
    assert all(value == 0 for value in settled["factor_attribution"].values())


def test_hypothetical_settlement_id_cannot_collide_with_actual_closing_instrument():
    asset = _bond(face=100_000, coupon=.04, maturity=date(2025, 6, 30))
    closing = _portfolio(Asset("SYN-ATTR-SETTLEMENT", "equity", "HKD", date(2025, 8, 1), 1000))
    result = attribute_movement(_portfolio(asset), closing, cashflow_policy="cash_no_interest")
    assert result["settlement_cash_asset_id"] != closing.assets[0].asset_id
    assert result["status"] == "complete"


def test_original_large_movement_exception_still_blocks_a_reconciling_bridge():
    opening = _portfolio(Asset("SYN-EQ", "equity", "HKD", DATE, 1_000_000))
    closing = _portfolio(Asset("SYN-EQ", "equity", "HKD", date(2025, 7, 1), 10_000_000))
    result = attribute_movement(opening, closing)
    assert result["status"] == "blocked"
    assert result["unexplained_residual"] == 0
    assert result["factor_attribution"]["holdings_and_equity_value"] == 2_700_000
    assert not next(check for check in result["validation"]["checks"] if check["name"] == "original_comparison_validation")["passed"]


def test_date_policy_and_original_mark_validation_are_enforced():
    asset = _bond()
    opening = _portfolio(asset)
    closing = _portfolio(replace(asset, valuation_date=date(2025, 7, 1)))
    for operation in (lambda: attribute_same_date(opening, closing), lambda: attribute_movement(opening, opening),
                      lambda: attribute_movement(opening, closing, cashflow_policy="automatic"),
                      lambda: attribute_same_date(_portfolio(replace(asset, market_value=1)), opening)):
        with pytest.raises(ValidationError):
            operation()
