"""Strict, synthetic-only portfolio inputs for the illustrative calculation engine.

Rates use decimal annual effective units, spreads use basis points, and all
amounts use HKD. The parser deliberately rejects extra columns and non-applicable
values so an upload cannot silently change the model's meaning.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any


CSV_COLUMNS = (
    "asset_id", "asset_type", "currency", "valuation_date", "market_value",
    "face_value", "coupon_rate", "yield_rate", "maturity_date", "credit_spread_bps",
)
MAX_FILE_BYTES = 2_000_000
MAX_ASSETS = 10_000
ASSET_TYPES = frozenset({"bond", "equity", "cash"})


class ValidationError(ValueError):
    """Input data are invalid; callers must not mark this analysis complete."""


def finite_number(value: Any, name: str, *, minimum: float | None = None) -> float:
    """Validate numeric model inputs, including direct Python API calls."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be a finite number (booleans are invalid)")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValidationError(f"{name} must be representable as a finite number") from exc
    if not math.isfinite(number):
        raise ValidationError(f"{name} must be finite")
    if minimum is not None and number < minimum:
        raise ValidationError(f"{name} must be >= {minimum}")
    return number


@dataclass(frozen=True)
class Asset:
    asset_id: str
    asset_type: str
    currency: str
    valuation_date: date
    market_value: float | None = None
    face_value: float | None = None
    coupon_rate: float | None = None
    yield_rate: float | None = None
    maturity_date: date | None = None
    credit_spread_bps: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", self.asset_id):
            raise ValidationError("asset_id must contain 1-64 ASCII letters, digits, dots, underscores or hyphens")
        if not isinstance(self.asset_type, str) or self.asset_type not in ASSET_TYPES:
            raise ValidationError(f"{self.asset_id}: asset_type must be bond, equity or cash")
        if self.currency != "HKD":
            raise ValidationError(f"{self.asset_id}: only HKD is supported in this prototype")
        if type(self.valuation_date) is not date:
            raise ValidationError(f"{self.asset_id}: valuation_date must be a date")
        if self.market_value is not None:
            finite_number(self.market_value, "market_value", minimum=0)
        if self.asset_type == "bond":
            for name in ("face_value", "coupon_rate", "yield_rate", "credit_spread_bps"):
                if getattr(self, name) is None:
                    raise ValidationError(f"{self.asset_id}: {name} is required for bonds")
            if finite_number(self.face_value, "face_value", minimum=0) == 0:
                raise ValidationError(f"{self.asset_id}: face_value must be positive")
            coupon = finite_number(self.coupon_rate, "coupon_rate", minimum=0)
            if coupon > 1:
                raise ValidationError("coupon_rate must be a decimal between 0 and 1")
            rate = finite_number(self.yield_rate, "yield_rate")
            spread = finite_number(self.credit_spread_bps, "credit_spread_bps", minimum=0)
            if rate <= -0.95 or rate + spread / 10_000 <= -0.95:
                raise ValidationError("bond yields must exceed -95% for the configured stresses")
            if type(self.maturity_date) is not date or self.maturity_date <= self.valuation_date:
                raise ValidationError(f"{self.asset_id}: maturity_date must be after valuation_date")
            if (self.maturity_date - self.valuation_date).days > 36525:
                raise ValidationError(f"{self.asset_id}: remaining maturity cannot exceed 100 years")
        else:
            if self.market_value is None:
                raise ValidationError(f"{self.asset_id}: market_value is required")
            for name in ("face_value", "coupon_rate", "yield_rate", "maturity_date", "credit_spread_bps"):
                if getattr(self, name) is not None:
                    raise ValidationError(f"{self.asset_id}: {name} must be blank for {self.asset_type}")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["valuation_date"] = self.valuation_date.isoformat()
        result["maturity_date"] = self.maturity_date.isoformat() if self.maturity_date else None
        return result


@dataclass(frozen=True)
class Portfolio:
    assets: tuple[Asset, ...]
    valuation_date: date
    currency: str = "HKD"

    def __post_init__(self) -> None:
        if not isinstance(self.assets, tuple) or not self.assets:
            raise ValidationError("portfolio must contain a nonempty tuple of assets")
        if len(self.assets) > MAX_ASSETS:
            raise ValidationError(f"portfolio exceeds {MAX_ASSETS} assets")
        if type(self.valuation_date) is not date or self.currency != "HKD":
            raise ValidationError("portfolio requires a valuation date and HKD currency")
        identifiers: set[str] = set()
        for asset in self.assets:
            if not isinstance(asset, Asset):
                raise ValidationError("portfolio assets must be Asset objects")
            if asset.asset_id in identifiers:
                raise ValidationError(f"duplicate asset_id: {asset.asset_id}")
            identifiers.add(asset.asset_id)
            if asset.valuation_date != self.valuation_date:
                raise ValidationError("all rows in one portfolio must have the same valuation_date")
            if asset.currency != self.currency:
                raise ValidationError("all portfolio currencies must agree")

    def to_dict(self) -> dict[str, Any]:
        return {"valuation_date": self.valuation_date.isoformat(), "currency": self.currency,
                "assets": [asset.to_dict() for asset in self.assets]}


def _parse_date(value: str, field: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValidationError(f"{field} must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{field} is not a valid date") from exc


def _parse_number(value: str, field: str) -> float | None:
    if not value:
        return None
    try:
        result = float(value)
    except ValueError as exc:
        raise ValidationError(f"{field} must be numeric") from exc
    return finite_number(result, field)


def load_portfolio_csv(source: str | bytes | Path) -> Portfolio:
    """Load a CSV path or CSV text/bytes, raising ValidationError on any issue.

    Synthetic provenance is a deployment constraint; it cannot be proved from
    a file's contents. The UI must instruct users to upload synthetic data only.
    """
    try:
        if isinstance(source, bytes):
            raw = source
        elif isinstance(source, Path):
            if source.stat().st_size > MAX_FILE_BYTES:
                raise ValidationError("portfolio upload exceeds 2 MB")
            raw = source.read_bytes()
        elif isinstance(source, str):
            if "\n" in source or "," in source:
                raw = source.encode("utf-8")
            else:
                path = Path(source)
                if path.stat().st_size > MAX_FILE_BYTES:
                    raise ValidationError("portfolio upload exceeds 2 MB")
                raw = path.read_bytes()
        else:
            raise ValidationError("source must be a CSV path, text or bytes")
    except (OSError, UnicodeError) as exc:
        raise ValidationError("could not read the portfolio CSV") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise ValidationError("portfolio upload exceeds 2 MB")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValidationError("portfolio CSV must be UTF-8") from exc
    if "\x00" in content:
        raise ValidationError("portfolio CSV contains a NUL character")
    try:
        reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
        if reader.fieldnames != list(CSV_COLUMNS):
            raise ValidationError("CSV columns must exactly match: " + ",".join(CSV_COLUMNS))
        assets: list[Asset] = []
        for row_number, raw_row in enumerate(reader, start=2):
            if len(assets) >= MAX_ASSETS:
                raise ValidationError(f"portfolio exceeds {MAX_ASSETS} assets")
            if None in raw_row or any(value is None for value in raw_row.values()):
                raise ValidationError(f"row {row_number}: wrong number of columns")
            row = {key: value.strip() for key, value in raw_row.items()}
            try:
                assets.append(Asset(
                    asset_id=row["asset_id"], asset_type=row["asset_type"], currency=row["currency"],
                    valuation_date=_parse_date(row["valuation_date"], "valuation_date"),
                    market_value=_parse_number(row["market_value"], "market_value"),
                    face_value=_parse_number(row["face_value"], "face_value"),
                    coupon_rate=_parse_number(row["coupon_rate"], "coupon_rate"),
                    yield_rate=_parse_number(row["yield_rate"], "yield_rate"),
                    maturity_date=_parse_date(row["maturity_date"], "maturity_date") if row["maturity_date"] else None,
                    credit_spread_bps=_parse_number(row["credit_spread_bps"], "credit_spread_bps"),
                ))
            except ValidationError as exc:
                raise ValidationError(f"row {row_number}: {exc}") from exc
    except csv.Error as exc:
        raise ValidationError(f"malformed CSV: {exc}") from exc
    if not assets:
        raise ValidationError("portfolio contains no asset rows")
    portfolio = Portfolio(tuple(assets), assets[0].valuation_date)
    # Import here avoids a module cycle and keeps price consistency enforced at
    # both the upload boundary and the direct calculation API boundary.
    from .calculations import validate_portfolio_prices

    validate_portfolio_prices(portfolio)
    return portfolio
