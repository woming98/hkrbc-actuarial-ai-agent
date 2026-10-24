"""Original deterministic, illustrative actuarial functions (not HK RBC rules).

No language model participates in valuation, stress, aggregation or validation.
All capital outputs are simplified teaching examples, not compliant regulatory
capital. In particular, there are no liabilities, matching adjustments, ratings,
currencies, tax effects or prescribed HK RBC calibration in this engine.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from calendar import monthrange
from datetime import date
from typing import Any, Iterable, Mapping

from .portfolio import Asset, Portfolio, ValidationError, finite_number


FUNCTION_VERSION = "1.0.0"
MODEL_LABEL = "Illustrative capital only — not HK RBC compliant"
MODULES = ("rate", "credit", "equity")
# Strictly diagonally dominant, symmetric positive-definite matrix. This is an
# internal illustrative choice, not a correlation prescribed by the HK IA.
CORRELATION = ((1.0, 0.25, 0.25), (0.25, 1.0, 0.5), (0.25, 0.5, 1.0))
KEY_RATE_NODES = (1.0, 2.0, 5.0, 10.0, 20.0, 30.0)
RATE_SHOCK = 0.01
CREDIT_SHOCK_BPS = 100.0
EQUITY_SHOCK = 0.30
PV_TOLERANCE_HKD = 0.01
LIMITATIONS = [
    MODEL_LABEL,
    "Assets only: no insurance liabilities, hedges, tax, operational risk, concentration or FX risk.",
    "Annual fixed coupons; dirty bond PV; no accrued-interest or business-day adjustment; ACT/365.25 discount times.",
    "Flat annual effective yields, additive yield/spread stresses, no default, recovery or migration model.",
    "Interest rate stress +/-100 bp; credit spread stress +100 bp; equity stress -30%; internally chosen calibration.",
    "The correlation matrix is illustrative and must not be represented as an HK RBC regulatory parameter.",
]


def _safe(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValidationError(f"{label} produced an unrepresentable result") from exc
    if not math.isfinite(number):
        raise ValidationError(f"{label} produced a non-finite result")
    return number


def _sum(values: Iterable[float]) -> float:
    try:
        return _safe(math.fsum(values), "numeric sum")
    except (OverflowError, ValueError) as exc:
        raise ValidationError("numeric aggregation produced a non-finite result") from exc


def _cashflows(face_value: float, coupon_rate: float, maturity_years: float) -> tuple[tuple[float, float], ...]:
    face = finite_number(face_value, "face_value", minimum=0)
    coupon = finite_number(coupon_rate, "coupon_rate", minimum=0)
    maturity = finite_number(maturity_years, "maturity_years", minimum=0)
    if face == 0 or maturity == 0 or maturity > 100 or coupon > 1:
        raise ValidationError("face_value and maturity_years must be positive; maturity <= 100 and coupon <= 1")
    # Coupon anniversaries run backwards from maturity. A fractional first
    # interval retains a full coupon (dirty-PV convention; no accrual model).
    count = math.ceil(maturity - 1e-12)
    times = sorted(maturity - index for index in range(count))
    return tuple((time, face * coupon + (face if index == len(times) - 1 else 0))
                 for index, time in enumerate(times))


def _discount(cashflows: Iterable[tuple[float, float]], yield_rate: float) -> float:
    rate = finite_number(yield_rate, "yield_rate")
    if rate <= -1:
        raise ValidationError("annual effective yield must exceed -100%")
    try:
        price = _sum(amount * math.exp(-time * math.log1p(rate)) for time, amount in cashflows)
    except (OverflowError, ValueError) as exc:
        raise ValidationError("yield and maturity cause an unrepresentable bond value") from exc
    price = _safe(price, "bond valuation")
    if price <= 0:
        raise ValidationError("bond value must be strictly positive")
    return price


def bond_price(face_value: float, coupon_rate: float, yield_rate: float, maturity_years: float) -> float:
    """Annual dirty PV; fractional first period pays a full annual coupon.

    The portfolio API uses actual maturity-anniversary dates instead; this
    duration-in-years helper exists for transparent mathematical unit cases.
    """
    return _discount(_cashflows(face_value, coupon_rate, maturity_years), yield_rate)


def _metrics(cashflows: tuple[tuple[float, float], ...], yield_rate: float) -> dict[str, float]:
    rate = finite_number(yield_rate, "yield_rate")
    price = _discount(cashflows, rate)
    weighted_time = _sum(time * amount * math.exp(-time * math.log1p(rate))
                              for time, amount in cashflows)
    macaulay = _safe(weighted_time / price, "Macaulay duration")
    modified = _safe(macaulay / (1 + rate), "modified duration")
    return {"price": price, "macaulay_duration": macaulay, "modified_duration": modified,
            "dv01": _safe(price * modified * 0.0001, "DV01")}


def bond_metrics(face_value: float, coupon_rate: float, yield_rate: float, maturity_years: float) -> dict[str, float]:
    return _metrics(_cashflows(face_value, coupon_rate, maturity_years), yield_rate)


def _anniversary(original: date, year: int) -> date:
    return date(year, original.month, min(original.day, monthrange(year, original.month)[1]))


def bond_cashflows(asset: Asset) -> tuple[tuple[float, float], ...]:
    """Future annual maturity anniversaries, excluding valuation-date payments."""
    if not isinstance(asset, Asset) or asset.asset_type != "bond":
        raise ValidationError("bond_cashflows requires a validated bond Asset")
    maturity = asset.maturity_date
    assert maturity is not None and asset.face_value is not None and asset.coupon_rate is not None
    future_dates = []
    for year in range(asset.valuation_date.year, maturity.year + 1):
        payment_date = _anniversary(maturity, year)
        if asset.valuation_date < payment_date <= maturity:
            future_dates.append(payment_date)
    return tuple(((payment_date - asset.valuation_date).days / 365.25,
                  asset.face_value * asset.coupon_rate + (asset.face_value if payment_date == maturity else 0))
                 for payment_date in future_dates)


def _bond_yield(asset: Asset) -> float:
    assert asset.yield_rate is not None and asset.credit_spread_bps is not None
    return asset.yield_rate + asset.credit_spread_bps / 10_000


def asset_value(asset: Asset, *, rate_shift: float = 0.0, spread_shift_bps: float = 0.0,
                equity_return: float = 0.0) -> float:
    rate = finite_number(rate_shift, "rate_shift")
    spread = finite_number(spread_shift_bps, "spread_shift_bps")
    equity = finite_number(equity_return, "equity_return")
    if equity < -1:
        raise ValidationError("equity_return cannot be less than -100%")
    if asset.asset_type == "bond":
        return _discount(bond_cashflows(asset), _bond_yield(asset) + rate + spread / 10_000)
    assert asset.market_value is not None
    return _safe(asset.market_value * (1 + equity if asset.asset_type == "equity" else 1), "asset valuation")


def validate_portfolio_prices(portfolio: Portfolio) -> None:
    if not isinstance(portfolio, Portfolio):
        raise ValidationError("a validated Portfolio is required")
    for asset in portfolio.assets:
        if asset.asset_type == "bond" and asset.market_value is not None:
            calculated = asset_value(asset)
            tolerance = max(PV_TOLERANCE_HKD, calculated * 1e-8)
            if abs(asset.market_value - calculated) > tolerance:
                raise ValidationError(f"{asset.asset_id}: supplied bond market_value disagrees with deterministic PV "
                                      f"(tolerance HKD {tolerance:.4f}); leave it blank to derive PV")


def _key_weights(time: float, nodes: tuple[float, ...]) -> tuple[float, ...]:
    if time <= nodes[0]:
        return (1.0,) + (0.0,) * (len(nodes) - 1)
    if time >= nodes[-1]:
        return (0.0,) * (len(nodes) - 1) + (1.0,)
    weights = [0.0] * len(nodes)
    for index in range(len(nodes) - 1):
        if nodes[index] <= time <= nodes[index + 1]:
            fraction = (time - nodes[index]) / (nodes[index + 1] - nodes[index])
            weights[index], weights[index + 1] = 1 - fraction, fraction
            break
    return tuple(weights)


def _key_rate_durations(cashflows: tuple[tuple[float, float], ...], yield_rate: float,
                        nodes: tuple[float, ...] = KEY_RATE_NODES) -> dict[str, float]:
    if not isinstance(nodes, tuple) or not nodes:
        raise ValidationError("key-rate nodes must be a nonempty tuple")
    checked = tuple(finite_number(node, "key-rate node", minimum=0) for node in nodes)
    if checked[0] <= 0 or checked != tuple(sorted(set(checked))):
        raise ValidationError("key-rate nodes must be positive and strictly increasing")
    base = _discount(cashflows, yield_rate)
    # Exact local derivative of a linearly interpolated annual-effective zero
    # curve. Node weights partition unity, so KRDs sum to modified duration.
    durations = []
    for node_index in range(len(nodes)):
        duration = _sum(time * amount * math.exp(-time * math.log1p(yield_rate))
                             * _key_weights(time, checked)[node_index] / (1 + yield_rate)
                             for time, amount in cashflows) / base
        durations.append(_safe(duration, "key-rate duration"))
    return {f"{node:g}y": duration for node, duration in zip(checked, durations)}


def key_rate_durations(face_value: float, coupon_rate: float, yield_rate: float,
                       maturity_years: float, nodes: tuple[float, ...] = KEY_RATE_NODES) -> dict[str, float]:
    return _key_rate_durations(_cashflows(face_value, coupon_rate, maturity_years), yield_rate, nodes)


def _modules(values: Mapping[str, float]) -> tuple[float, float, float]:
    if not isinstance(values, Mapping) or set(values) != set(MODULES):
        raise ValidationError("capital modules must contain exactly rate, credit and equity")
    return tuple(finite_number(values[name], f"{name} capital", minimum=0) for name in MODULES)  # type: ignore[return-value]


def aggregate_capital(module_capital: Mapping[str, float]) -> float:
    """sqrt(c.T @ correlation @ c), using the fixed illustrative PSD matrix."""
    values = _modules(module_capital)
    scale = max(values)
    if scale == 0:
        return 0.0
    normalized = tuple(value / scale for value in values)
    squared = _sum(normalized[i] * CORRELATION[i][j] * normalized[j]
                        for i in range(3) for j in range(3))
    return _safe(scale * math.sqrt(max(0.0, squared)), "capital aggregation")


def shapley_movement(opening: Mapping[str, float], closing: Mapping[str, float]) -> dict[str, float]:
    """Exact three-player Shapley attribution, enumerating all six orderings.

    Each marginal substitutes a closing module into a hybrid capital vector.
    Summing attributions telescopes to the total diversified-capital change.
    """
    _modules(opening)
    _modules(closing)
    increments: dict[str, list[float]] = {module: [] for module in MODULES}
    for ordering in itertools.permutations(MODULES):
        hybrid = dict(opening)
        previous = aggregate_capital(hybrid)
        for module in ordering:
            hybrid[module] = closing[module]
            current = aggregate_capital(hybrid)
            increments[module].append(current - previous)
            previous = current
    return {module: _sum(value / 6 for value in increments[module]) for module in MODULES}


def _check(name: str, passed: bool, details: str, *, severity: str = "error") -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "severity": severity, "details": details}


def _record(function: str, inputs: Any, outputs: Any, checks: list[dict[str, Any]],
            assumptions: list[str]) -> dict[str, Any]:
    return {"function": function, "version": FUNCTION_VERSION, "inputs": inputs, "outputs": outputs,
            "assumptions": assumptions, "validation": {"passed": all(item["passed"] for item in checks), "checks": checks},
            "limitations": list(LIMITATIONS)}


def _fingerprint(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def analyse_portfolio(portfolio: Portfolio) -> dict[str, Any]:
    """Validate and calculate one synthetic asset-only portfolio deterministically."""
    validate_portfolio_prices(portfolio)
    assets = []
    records = []
    checks = [_check("input_schema", True, "Strict validated nonempty HKD portfolio; finite inputs and unique IDs.")]
    for asset in portfolio.assets:
        base = asset_value(asset)
        up = asset_value(asset, rate_shift=RATE_SHOCK)
        down = asset_value(asset, rate_shift=-RATE_SHOCK)
        spread = asset_value(asset, spread_shift_bps=CREDIT_SHOCK_BPS)
        equity = asset_value(asset, equity_return=-EQUITY_SHOCK)
        row: dict[str, Any] = {"asset_id": asset.asset_id, "asset_type": asset.asset_type,
                               "market_value": base, "rate_up_value": up, "rate_down_value": down,
                               "credit_stress_value": spread, "equity_stress_value": equity}
        row_checks = [_check("finite_nonnegative_values", all(math.isfinite(value) and value >= 0
                            for value in (base, up, down, spread, equity)), "All scenario asset values are finite and nonnegative.")]
        if asset.asset_type == "bond":
            metrics = _metrics(bond_cashflows(asset), _bond_yield(asset))
            krd = _key_rate_durations(bond_cashflows(asset), _bond_yield(asset))
            row.update(metrics)
            row["key_rate_durations"] = krd
            row["cashflows"] = [{"time_years": time, "amount_hkd": amount} for time, amount in bond_cashflows(asset)]
            row_checks += [
                _check("bond_price_monotonicity", down >= base >= up and spread <= base,
                       "Positive bond cashflows decrease in value when yield/spread rises."),
                _check("key_rate_duration_reconciliation", math.isclose(_sum(krd.values()), metrics["modified_duration"], rel_tol=1e-12, abs_tol=1e-12),
                       "The interpolated node weights partition unity; KRD sums to modified duration."),
            ]
        records.append(_record("value_and_stress_asset", asset.to_dict(), row, row_checks,
                               ["Annual effective risk-free yield plus spread/10000.",
                                "Full annual coupons on future maturity anniversaries; maturity payment includes principal."]))
        checks.extend({**item, "asset_id": asset.asset_id} for item in row_checks)
        assets.append(row)
    base_total = _safe(_sum(row["market_value"] for row in assets), "portfolio value")
    rate_up = _safe(_sum(row["rate_up_value"] for row in assets), "rate-up value")
    rate_down = _safe(_sum(row["rate_down_value"] for row in assets), "rate-down value")
    credit_value = _safe(_sum(row["credit_stress_value"] for row in assets), "credit-stress value")
    equity_value = _safe(_sum(row["equity_stress_value"] for row in assets), "equity-stress value")
    # Sum per-asset losses to avoid cancellation when riskless cash greatly
    # exceeds a small risky exposure. Rate stresses still aggregate at portfolio
    # level before choosing the worst direction.
    capital = {"rate": max(0.0, _sum(row["market_value"] - row["rate_up_value"] for row in assets),
                           _sum(row["market_value"] - row["rate_down_value"] for row in assets)),
               "credit": max(0.0, _sum(row["market_value"] - row["credit_stress_value"] for row in assets)),
               "equity": max(0.0, _sum(row["market_value"] - row["equity_stress_value"] for row in assets))}
    aggregate = aggregate_capital(capital)
    module_sum = _safe(_sum(capital.values()), "sum of standalone capital")
    aggregate_checks = [
        _check("capital_bounds", max(capital.values()) <= aggregate + 1e-7 and aggregate <= module_sum + 1e-7,
               "Illustrative correlation aggregation lies between the largest module and their sum."),
        _check("aggregation_reconciliation", math.isclose(aggregate,
               math.hypot(capital["rate"] + 0.25 * capital["credit"] + 0.25 * capital["equity"],
                          math.sqrt(15 / 16) * capital["credit"] + (7 / (4 * math.sqrt(15))) * capital["equity"],
                          math.sqrt(11 / 15) * capital["equity"]), rel_tol=1e-12, abs_tol=1e-6),
               "Capital reconciles independently to the Cholesky norm of the illustrative correlation matrix."),
    ]
    checks.extend(aggregate_checks)
    records.append(_record("aggregate_capital", {"module_capital": capital, "correlation": CORRELATION},
                           {"aggregate_capital": aggregate}, aggregate_checks,
                           ["Fixed internally chosen positive-definite correlation matrix; no regulatory calibration."]))
    passed = all(item["passed"] for item in checks)
    payload = {"status": "complete" if passed else "blocked", "model_label": MODEL_LABEL,
               "function_version": FUNCTION_VERSION, "currency": "HKD", "valuation_date": portfolio.valuation_date.isoformat(),
               "total_market_value": base_total, "module_capital": capital, "aggregate_capital": aggregate,
               "stress_values": {"rate_up": rate_up, "rate_down": rate_down, "credit": credit_value, "equity": equity_value},
               "standalone_capital_sum": module_sum, "diversification_benefit": module_sum - aggregate,
               "portfolio_dv01": _sum(row.get("dv01", 0.0) for row in assets),
               "assets": assets, "validation": {"passed": passed, "checks": checks},
               "calculations": records, "limitations": list(LIMITATIONS),
               "input_fingerprint": _fingerprint(portfolio.to_dict())}
    payload["report_id"] = "portfolio-" + _fingerprint(payload)[:16]
    return payload


def compare_portfolios(opening: Portfolio, closing: Portfolio, *, materiality_hkd: float = 100_000.0,
                       unexpected_movement_ratio: float = 0.5) -> dict[str, Any]:
    """Compare dates; reconcile diversification using exact Shapley attribution.

    A large relative movement raises a deterministic review exception, blocks
    completion, and remains visible in the report. It is not silently accepted.
    """
    materiality = finite_number(materiality_hkd, "materiality_hkd", minimum=0)
    threshold = finite_number(unexpected_movement_ratio, "unexpected_movement_ratio", minimum=0)
    if closing.valuation_date <= opening.valuation_date:
        raise ValidationError("closing valuation_date must be after opening valuation_date")
    start, end = analyse_portfolio(opening), analyse_portfolio(closing)
    attribution = shapley_movement(start["module_capital"], end["module_capital"])
    movement = end["aggregate_capital"] - start["aggregate_capital"]
    explained = _sum(attribution.values())
    residual = movement - explained
    raw_changes = {module: end["module_capital"][module] - start["module_capital"][module] for module in MODULES}
    change_ratio = abs(movement) / start["aggregate_capital"] if start["aggregate_capital"] else (0.0 if movement == 0 else None)
    unexpected = abs(movement) > materiality and (change_ratio is None or change_ratio > threshold)
    checks = [
        _check("opening_validation", start["validation"]["passed"], "Opening portfolio deterministic checks."),
        _check("closing_validation", end["validation"]["passed"], "Closing portfolio deterministic checks."),
        _check("movement_reconciliation", math.isclose(movement, explained, rel_tol=1e-10, abs_tol=0.01),
               f"Exact Shapley allocation residual: HKD {residual:.10f}; tolerance HKD 0.01."),
        _check("unexpected_movement_review", not unexpected,
               f"Review required if absolute change exceeds HKD {materiality:g} and relative change exceeds {threshold:.0%}; opening zero with material increase also requires review."),
    ]
    opening_ids = {asset.asset_id for asset in opening.assets}
    closing_ids = {asset.asset_id for asset in closing.assets}
    exposures = {asset_type: {"opening": _sum(asset_value(asset) for asset in opening.assets if asset.asset_type == asset_type),
                             "closing": _sum(asset_value(asset) for asset in closing.assets if asset.asset_type == asset_type)}
                 for asset_type in ("bond", "equity", "cash")}
    drivers = [{"module": module, "standalone_change_hkd": raw_changes[module],
                "shapley_change_hkd": attribution[module], "material": abs(attribution[module]) >= materiality,
                "description": {"rate": "Change in bond exposure, remaining cashflows and yields under +/-100 bp rate stress.",
                                "credit": "Change in bond exposure, remaining cashflows and yields under +100 bp spread stress.",
                                "equity": "Change in equity market value under the illustrative 30% equity shock."}[module]}
               for module in MODULES]
    passed = all(item["passed"] for item in checks)
    record = _record("compare_portfolios_exact_shapley", {"opening_modules": start["module_capital"], "closing_modules": end["module_capital"],
                     "materiality_hkd": materiality, "unexpected_movement_ratio": threshold},
                     {"capital_movement": movement, "shapley_attribution": attribution, "unexplained_residual": residual}, checks,
                     ["All 6 module orderings have equal weight.", "This allocates changes among risk modules, not causal transaction-level drivers."])
    payload = {"status": "complete" if passed else "blocked", "model_label": MODEL_LABEL,
               "currency": "HKD", "function_version": FUNCTION_VERSION, "opening": start, "closing": end,
               "capital_movement": movement, "relative_movement": change_ratio,
               "module_changes": raw_changes, "shapley_attribution": attribution,
               "explained_movement": explained, "unexplained_residual": residual,
               "diversification_movement": end["diversification_benefit"] - start["diversification_benefit"],
               "drivers": drivers, "exposure_changes": exposures,
               "added_asset_ids": sorted(closing_ids - opening_ids), "removed_asset_ids": sorted(opening_ids - closing_ids),
               "validation": {"passed": passed, "checks": checks}, "calculations": [record], "limitations": list(LIMITATIONS)}
    payload["report_id"] = "movement-" + _fingerprint(payload)[:16]
    return payload


def generate_scenarios(portfolio: Portfolio, count: int = 100, seed: int = 42) -> dict[str, Any]:
    """Seeded illustrative one-year shocks, using only a local Random instance.

    Simple independent normals and lognormal equity returns are demonstration
    inputs, not an ESG calibrated to market data or regulatory requirements.
    """
    validate_portfolio_prices(portfolio)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 1000:
        raise ValidationError("scenario count must be an integer between 1 and 1000")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise ValidationError("scenario seed must be an integer in [0, 2**32 - 1]")
    rng = random.Random(seed)
    base = _safe(_sum(asset_value(asset) for asset in portfolio.assets), "base scenario value")
    minimum_yield = min((_bond_yield(asset) for asset in portfolio.assets if asset.asset_type == "bond"), default=0.0)
    rows = []
    for index in range(count):
        rate_shift = rng.gauss(0.0, 0.01)
        spread_shift = max(-50.0, rng.gauss(0.0, 50.0))
        equity_return = math.expm1(rng.gauss(-0.5 * 0.20**2, 0.20))
        # Keep the stressed annual yield above -95%; preserve a visible record
        # if the normal draw is clipped. This is a numerical demo guard only.
        floor = -0.95 - minimum_yield - spread_shift / 10_000 + 1e-10
        clipped = rate_shift < floor
        rate_shift = max(rate_shift, floor)
        value = _safe(_sum(asset_value(asset, rate_shift=rate_shift,
                                           spread_shift_bps=spread_shift, equity_return=equity_return)
                                for asset in portfolio.assets), "scenario portfolio value")
        rows.append({"scenario_id": index + 1, "rate_shift": rate_shift,
                     "spread_shift_bps": spread_shift, "equity_return": equity_return,
                     "portfolio_value": value, "pnl": value - base, "yield_floor_applied": clipped})
    checks = [
        _check("scenario_count", len(rows) == count, "Requested count generated."),
        _check("scenario_unique_ids", len({row["scenario_id"] for row in rows}) == count, "Scenario IDs unique."),
        _check("scenario_finite_outputs", all(math.isfinite(row[key]) for row in rows
                for key in ("rate_shift", "spread_shift_bps", "equity_return", "portfolio_value", "pnl")), "All values finite."),
        _check("scenario_nonnegative_values", all(row["portfolio_value"] >= 0 and row["equity_return"] > -1 for row in rows),
               "Portfolio values nonnegative; equity returns exceed -100%."),
        _check("scenario_pnl_reconciliation", all(math.isclose(row["pnl"], row["portfolio_value"] - base, abs_tol=1e-8) for row in rows),
               "Each P&L reconciles to stressed value less base value."),
    ]
    passed = all(item["passed"] for item in checks)
    result = {"status": "complete" if passed else "blocked", "model_label": MODEL_LABEL, "seed": seed,
              "count": count, "currency": "HKD", "base_portfolio_value": base, "scenarios": rows,
              "validation": {"passed": passed, "checks": checks}, "limitations": list(LIMITATIONS) +
              ["Independent illustrative one-year shocks; no probability-of-default or risk-neutral calibration; values reprice current cashflows without time roll-forward."],
              "input_fingerprint": _fingerprint(portfolio.to_dict()), "function_version": FUNCTION_VERSION}
    result["calculations"] = [_record("generate_scenarios", {"count": count, "seed": seed, "portfolio": portfolio.to_dict()},
                                        {"scenario_digest": _fingerprint(rows), "count": count}, checks,
                                        ["Python random.Random (Mersenne Twister), local seed; reproducibility within the documented Python environment.",
                                         "Normal rate sigma 1%; normal spread sigma 50bp with -50bp floor; equity log-return sigma 20% and mean -0.5*sigma²."])]
    return result
