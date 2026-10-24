"""Independent identities, stress invariants and exact diversification reconciliation."""

import json
import math
import random
from datetime import date
from pathlib import Path

import pytest

from hkrbc_agent.calculations import (
    CORRELATION, aggregate_capital, analyse_portfolio, asset_value, bond_cashflows,
    bond_metrics, bond_price, compare_portfolios, generate_scenarios,
    key_rate_durations, shapley_movement,
)
from hkrbc_agent.portfolio import Asset, Portfolio, ValidationError, load_portfolio_csv


DATA = Path(__file__).resolve().parents[1] / "data" / "portfolios"


def _equity(value, valuation_date=date(2025, 12, 31)):
    return Portfolio((Asset("SYN-EQ", "equity", "HKD", valuation_date, value),), valuation_date)


def test_zero_coupon_matches_closed_form_and_derivative():
    metrics = bond_metrics(1_000_000, 0.0, 0.05, 5.0)
    expected = 1_000_000 / 1.05**5
    assert metrics["price"] == pytest.approx(expected)
    assert metrics["macaulay_duration"] == pytest.approx(5)
    assert metrics["modified_duration"] == pytest.approx(5 / 1.05)
    assert metrics["dv01"] == pytest.approx(expected * 5 / 1.05 * 0.0001)
    bump = 0.000001
    finite_difference = (bond_price(1_000_000, 0, 0.05 - bump, 5) - bond_price(1_000_000, 0, 0.05 + bump, 5)) / (2 * bump)
    assert metrics["dv01"] == pytest.approx(finite_difference * 0.0001, rel=1e-8)


def test_par_bond_and_manual_coupon_discounting():
    assert bond_price(100, 0.04, 0.04, 10) == pytest.approx(100)
    expected = sum(4 / 1.05**year for year in range(1, 4)) + 100 / 1.05**3
    assert bond_price(100, 0.04, 0.05, 3) == pytest.approx(expected)
    # Fractional first dirty coupon is explicit; no invented prorated accrual.
    assert bond_price(100, 0.04, 0.05, 1.5) == pytest.approx(4 / 1.05**0.5 + 104 / 1.05**1.5)


def test_zero_and_negative_yields_and_monotone_prices():
    assert bond_price(100, 0, 0, 2) == 100
    assert bond_price(100, 0, -0.02, 2) > 100
    assert bond_price(100, 0.05, -0.01, 5) > bond_price(100, 0.05, 0.03, 5) > bond_price(100, 0.05, 0.10, 5)


@pytest.mark.parametrize("arguments", [(0, 0.04, 0.03, 3), (-100, 0.04, 0.03, 3),
    (100, -0.01, 0.03, 3), (100, 2, 0.03, 3), (100, 0.04, -1, 3),
    (100, 0.04, 0.03, 0), (100, 0.04, 0.03, 101), (True, 0.04, 0.03, 3),
    (100, float("nan"), 0.03, 3), (100, 0.04, float("inf"), 3)])
def test_bond_math_rejects_invalid_inputs(arguments):
    with pytest.raises(ValidationError):
        bond_price(*arguments)


def test_cashflows_use_actual_dates_and_handle_leap_anniversary():
    asset = Asset("SYN-LEAP", "bond", "HKD", date(2025, 2, 28), None, 100, 0.04, 0.03, date(2028, 2, 29), 0)
    flows = bond_cashflows(asset)
    assert len(flows) == 3  # Excludes the coupon exactly on valuation date.
    assert [amount for _, amount in flows] == [4, 4, 104]
    assert flows[-1][0] == pytest.approx((date(2028, 2, 29) - date(2025, 2, 28)).days / 365.25)
    expected = math.fsum(amount / 1.03**time for time, amount in flows)
    assert asset_value(asset) == pytest.approx(expected)


@pytest.mark.parametrize("maturity", [0.1, 1, 3.5, 10, 50, 100])
def test_key_rate_duration_partition_identity(maturity):
    duration = bond_metrics(1_000_000, 0.045, 0.03, maturity)["modified_duration"]
    key_rates = key_rate_durations(1_000_000, 0.045, 0.03, maturity)
    assert all(value >= 0 for value in key_rates.values())
    assert math.fsum(key_rates.values()) == pytest.approx(duration, rel=1e-12)


def test_zero_coupon_key_rate_at_exact_node_and_interpolation():
    exact = key_rate_durations(100, 0, 0.04, 5)
    assert exact["5y"] == pytest.approx(5 / 1.04)
    assert sum(value for key, value in exact.items() if key != "5y") == 0
    between = key_rate_durations(100, 0, 0.04, 3.5)
    assert between["2y"] == pytest.approx(between["5y"])


@pytest.mark.parametrize("nodes", [(), (2.0, 1.0), (1.0, 1.0), (-1.0, 2.0), (True, 2.0)])
def test_invalid_key_rate_nodes(nodes):
    with pytest.raises(ValidationError):
        key_rate_durations(100, 0.04, 0.03, 3, nodes)


def test_correlation_matrix_positive_definite_and_aggregation_independent_identity():
    # Sylvester criterion, independently checked without a numpy dependency.
    assert CORRELATION[0][0] > 0
    assert 1 - 0.25**2 > 0
    determinant = 1 + 2 * 0.25 * 0.25 * 0.5 - 0.25**2 - 0.25**2 - 0.5**2
    assert determinant > 0
    expected = math.sqrt(10**2 + 20**2 + 30**2 + 2 * .25 * 10 * 20 + 2 * .25 * 10 * 30 + 2 * .5 * 20 * 30)
    assert aggregate_capital({"rate": 10, "credit": 20, "equity": 30}) == pytest.approx(expected)
    assert aggregate_capital({"rate": 0, "credit": 0, "equity": 0}) == 0
    assert aggregate_capital({"rate": 0, "credit": 0, "equity": 25}) == 25


@pytest.mark.parametrize("modules", [{"rate": 1, "equity": 1}, {"rate": -1, "credit": 1, "equity": 1},
    {"rate": True, "credit": 1, "equity": 1}, {"rate": float("nan"), "credit": 1, "equity": 1}])
def test_aggregation_rejects_undefined_modules(modules):
    with pytest.raises(ValidationError):
        aggregate_capital(modules)


def test_shapley_exact_reconciliation_symmetric_and_zero_change_properties():
    rng = random.Random(7)
    for _ in range(100):
        start = {module: rng.uniform(0, 10_000_000) for module in ("rate", "credit", "equity")}
        end = {module: rng.uniform(0, 10_000_000) for module in ("rate", "credit", "equity")}
        attribution = shapley_movement(start, end)
        assert math.fsum(attribution.values()) == pytest.approx(aggregate_capital(end) - aggregate_capital(start), abs=1e-8)
        reversed_attribution = shapley_movement(end, start)
        assert all(attribution[module] == pytest.approx(-reversed_attribution[module], abs=1e-8) for module in start)
    unchanged = {"rate": 10, "credit": 20, "equity": 30}
    assert all(value == 0 for value in shapley_movement(unchanged, unchanged).values())
    moved = shapley_movement(unchanged, {**unchanged, "equity": 40})
    assert moved["rate"] == moved["credit"] == 0


def test_sample_movement_reconciles_diversification_and_has_audit_metadata():
    start, end = (load_portfolio_csv(DATA / name) for name in ("opening.csv", "closing.csv"))
    result = compare_portfolios(start, end)
    assert result["status"] == "complete"
    assert result["validation"]["passed"]
    assert result["capital_movement"] == pytest.approx(2_390_978.5932322517, abs=0.01)
    assert result["unexplained_residual"] == pytest.approx(0, abs=0.01)
    # Naive standalone module changes are intentionally not the aggregate move.
    assert sum(result["module_changes"].values()) != pytest.approx(result["capital_movement"])
    assert sum(result["module_changes"].values()) - result["diversification_movement"] == pytest.approx(result["capital_movement"])
    assert result["shapley_attribution"]["rate"] < 0 < result["shapley_attribution"]["equity"]
    for report in (result, result["opening"], result["closing"]):
        assert "not HK RBC compliant" in report["model_label"]
        for record in report["calculations"]:
            assert all(key in record for key in ("function", "version", "inputs", "outputs", "assumptions", "validation", "limitations"))
    assert json.dumps(result, allow_nan=False)
    assert compare_portfolios(start, end) == result


def test_cash_only_zero_capital_and_small_risky_exposure_beside_large_cash():
    when = date(2025, 12, 31)
    cash = Asset("SYN-CASH", "cash", "HKD", when, 1e18)
    assert analyse_portfolio(Portfolio((cash,), when))["aggregate_capital"] == 0
    equity = Asset("SYN-EQ", "equity", "HKD", when, 10)
    result = analyse_portfolio(Portfolio((cash, equity), when))
    assert result["module_capital"]["equity"] == 3
    assert result["aggregate_capital"] == 3


def test_unexpected_capital_movement_blocks_completion():
    start = _equity(1_000_000)
    end = _equity(10_000_000, date(2026, 1, 31))
    report = compare_portfolios(start, end)
    assert report["status"] == "blocked"
    assert not report["validation"]["passed"]
    assert any(check["name"] == "unexpected_movement_review" and not check["passed"] for check in report["validation"]["checks"])


def test_movement_date_order_zero_opening_and_parameter_validation():
    with pytest.raises(ValidationError, match="after"):
        compare_portfolios(_equity(100), _equity(200))
    report = compare_portfolios(_equity(0), _equity(10_000_000, date(2026, 1, 31)))
    assert report["relative_movement"] is None and report["status"] == "blocked"
    for kwargs in ({"materiality_hkd": -1}, {"materiality_hkd": True}, {"unexpected_movement_ratio": float("inf")}):
        with pytest.raises(ValidationError):
            compare_portfolios(_equity(1), _equity(2, date(2026, 1, 31)), **kwargs)


def test_direct_api_cannot_skip_supplied_price_validation():
    asset = Asset("SYN-BOND", "bond", "HKD", date(2025, 12, 31), 1, 100, 0.04, 0.03, date(2030, 12, 31), 100)
    with pytest.raises(ValidationError, match="disagrees"):
        analyse_portfolio(Portfolio((asset,), asset.valuation_date))


def test_unrepresentable_aggregate_is_a_controlled_validation_failure():
    when = date(2025, 12, 31)
    portfolio = Portfolio((Asset("SYN-CASH-1", "cash", "HKD", when, 1e308),
                           Asset("SYN-CASH-2", "cash", "HKD", when, 1e308)), when)
    with pytest.raises(ValidationError, match="non-finite"):
        analyse_portfolio(portfolio)


def test_seeded_scenario_integrity_reproducibility_and_no_global_rng_side_effect():
    portfolio = load_portfolio_csv(DATA / "opening.csv")
    random.seed(901)
    state = random.getstate()
    first = generate_scenarios(portfolio, 100, 42)
    assert random.getstate() == state
    assert first == generate_scenarios(portfolio, 100, 42)
    assert first != generate_scenarios(portfolio, 100, 43)
    assert first["status"] == "complete" and first["validation"]["passed"]
    assert len(first["scenarios"]) == 100
    for row in first["scenarios"]:
        assert row["portfolio_value"] >= 0
        assert row["equity_return"] > -1
        assert row["pnl"] == pytest.approx(row["portfolio_value"] - first["base_portfolio_value"])
    assert json.dumps(first, allow_nan=False)


@pytest.mark.parametrize("count,seed", [(True, 1), (0, 1), (1001, 1), (1.5, 1), (1, True), (1, -1), (1, 2**32), (1, 1.5)])
def test_invalid_scenario_parameters_block_calculation(count, seed):
    with pytest.raises(ValidationError):
        generate_scenarios(_equity(100), count, seed)
