"""Upload-boundary tests: invalid inputs must not become completed analyses."""

from datetime import date
from pathlib import Path

import pytest

from hkrbc_agent.portfolio import Asset, CSV_COLUMNS, Portfolio, ValidationError, finite_number, load_portfolio_csv


HEADER = ",".join(CSV_COLUMNS) + "\n"
VALID_EQUITY = "SYN-EQ,equity,HKD,2025-12-31,1000000,,,,,\n"
VALID_BOND = "SYN-BOND,bond,HKD,2025-12-31,,1000000,0.04,0.03,2030-12-31,100\n"
DATA = Path(__file__).resolve().parents[1] / "data" / "portfolios"


def test_synthetic_samples_and_utf8_bom():
    opening = load_portfolio_csv(DATA / "opening.csv")
    closing = load_portfolio_csv(str(DATA / "closing.csv"))
    assert len(opening.assets) == len(closing.assets) == 4
    assert opening.valuation_date < closing.valuation_date
    assert opening.to_dict()["assets"][0]["maturity_date"] == "2030-12-31"
    assert load_portfolio_csv(("\ufeff" + HEADER + VALID_EQUITY).encode()).assets[0].market_value == 1_000_000


@pytest.mark.parametrize("content", [
    "", HEADER, HEADER + VALID_EQUITY + VALID_EQUITY,
    HEADER + VALID_EQUITY.replace("1000000", "-1"),
    HEADER + VALID_EQUITY.replace("1000000", "NaN"),
    HEADER + VALID_EQUITY.replace("1000000", "inf"),
    HEADER + VALID_EQUITY.replace("1000000", "1e999"),
    HEADER + VALID_EQUITY.replace("1000000", "True"),
    HEADER + VALID_EQUITY.replace("HKD", "USD"),
    HEADER + VALID_EQUITY.replace("equity", "derivative"),
    HEADER + VALID_EQUITY.replace("2025-12-31", "2025-02-30"),
    HEADER + VALID_EQUITY.replace("2025-12-31", "20251231"),
    HEADER + VALID_EQUITY + VALID_BOND.replace("2025-12-31", "2025-12-30"),
    HEADER + VALID_EQUITY.replace("1000000,,,,,", "1000000,1,,,,"),
    HEADER + VALID_EQUITY.replace("1000000", ""),
    HEADER + VALID_BOND.replace("2030-12-31", "2025-12-31"),
    HEADER + VALID_BOND.replace(",,1000000,", ",1,1000000,"),
    HEADER + VALID_BOND.replace("0.04", "4.0"),
    HEADER + VALID_BOND.replace("0.03", "-0.96"),
    HEADER + VALID_BOND.replace(",100\n", ",-1\n"),
    HEADER + VALID_BOND.replace(",1000000,", ",-1000000,"),
    HEADER + VALID_BOND.replace("2030-12-31", "2200-12-31"),
    HEADER + VALID_BOND.replace("0.04", ""),
    HEADER + VALID_EQUITY.rstrip("\n") + ",extra\n",
    HEADER + VALID_EQUITY.replace(",,,,,\n", ",,,,\n"),
    HEADER.replace("asset_id", "unknown_id") + VALID_EQUITY,
    HEADER.replace("asset_type", "asset_id") + VALID_EQUITY,
    HEADER + VALID_EQUITY.replace("SYN-EQ", "\x00bad"),
    HEADER + VALID_EQUITY.replace("SYN-EQ", '=HYPERLINK("bad")'),
    HEADER + '"unterminated,equity,HKD,2025-12-31,1000000,,,,,\n',
])
def test_rejects_malformed_portfolios(content):
    with pytest.raises(ValidationError):
        load_portfolio_csv(content)


def test_rejects_unreadable_invalid_encoding_and_oversized_uploads(tmp_path):
    for source in (b"\xff", b"a" * 2_000_001, tmp_path / "missing.csv", 42):
        with pytest.raises(ValidationError):
            load_portfolio_csv(source)


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), -float("inf"), "1", 10**1000])
def test_finite_numeric_boundary_rejects_bool_nonfinite_and_unrepresentable(value):
    with pytest.raises(ValidationError):
        finite_number(value, "test")


def test_direct_dataclass_construction_enforces_dates_and_duplicates():
    asset = Asset("SYN-EQ", "equity", "HKD", date(2025, 12, 31), 1.0)
    with pytest.raises(ValidationError, match="duplicate"):
        Portfolio((asset, asset), asset.valuation_date)
    with pytest.raises(ValidationError, match="same valuation_date"):
        Portfolio((asset,), date(2026, 1, 1))
    with pytest.raises(ValidationError):
        Portfolio((), date(2025, 12, 31))
    with pytest.raises(ValidationError):
        Asset("SYN-EQ", "equity", "HKD", date(2025, 12, 31), True)


def test_supplied_price_can_reconcile_but_cannot_override_engine():
    from hkrbc_agent.calculations import asset_value

    original = load_portfolio_csv(HEADER + VALID_BOND)
    price = asset_value(original.assets[0])
    matched = VALID_BOND.replace(",,1000000,", f",{price:.8f},1000000,")
    assert load_portfolio_csv(HEADER + matched).assets[0].market_value == pytest.approx(price)
    with pytest.raises(ValidationError, match="disagrees"):
        load_portfolio_csv(HEADER + matched.replace(str(round(price, 8)), str(price + 100)))


def test_sample_malformed_has_a_real_validation_failure():
    with pytest.raises(ValidationError, match="duplicate"):
        load_portfolio_csv(DATA / "malformed.csv")
