"""Prices, simple returns, and constant-mix portfolio weights."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from market_risk.errors import MarketRiskError

# Illustrative long-only mix of public USD-listed ETFs. The weights are a
# demo book, not an allocation recommendation.
SAMPLE_WEIGHTS: dict[str, float] = {
    "SPY": 0.35,
    "EFA": 0.20,
    "EEM": 0.10,
    "AGG": 0.25,
    "GLD": 0.10,
}

TRADING_DAYS_PER_YEAR = 252


def bundled_sample_prices_path() -> Path:
    """Path to the recorded sample workbook shipped with this project."""
    path = Path(__file__).resolve().parents[2] / "data" / "sample_prices.csv"
    if not path.is_file():
        raise MarketRiskError(
            "could not find data/sample_prices.csv. Pass --prices with a CSV path."
        )
    return path


def load_prices(path: str | Path) -> pd.DataFrame:
    """Load a date-indexed table of positive prices.

    The CSV needs a ``date`` column and one column per ticker. Dates are sorted
    ascending. Missing, non-positive, and duplicate observations are rejected
    rather than filled.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise MarketRiskError(f"price file not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise MarketRiskError(f"price file is empty: {file_path}")

    columns = [str(column).strip() for column in frame.columns]
    frame.columns = columns
    date_name = next((column for column in columns if column.lower() == "date"), None)
    if date_name is None:
        raise MarketRiskError("price file needs a date column")

    dates = pd.to_datetime(frame[date_name], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any():
        raise MarketRiskError("price file has a date that could not be parsed")

    values = frame.drop(columns=[date_name])
    values.columns = [str(column).strip().upper() for column in values.columns]
    if values.shape[1] == 0:
        raise MarketRiskError("price file has no ticker columns")
    if values.columns.duplicated().any():
        raise MarketRiskError("price file has duplicate tickers")

    numeric = values.apply(pd.to_numeric, errors="coerce")
    prices = numeric.copy()
    prices.index = pd.DatetimeIndex(dates)
    prices.index.name = "date"
    prices = prices.sort_index()
    if prices.index.has_duplicates:
        raise MarketRiskError("price file has duplicate dates")
    if prices.isna().to_numpy().any():
        raise MarketRiskError("price file has a missing or non-numeric price")

    array = prices.to_numpy(dtype=float)
    if not np.isfinite(array).all():
        raise MarketRiskError("price file has a non-finite price")
    if np.any(array <= 0.0):
        raise MarketRiskError("prices must be positive")
    return prices


def align_weights(
    columns: pd.Index | list[str] | tuple[str, ...],
    weights: Mapping[str, float],
) -> pd.Series:
    """Align weights to price columns. Weights must be finite and sum to 1.

    Negative weights are allowed. They are short positions. Every ticker in
    the price table needs a weight, and every weight needs a price column, so
    an asset cannot be dropped silently.
    """
    if not weights:
        raise MarketRiskError("at least one weight is required")

    normalized: dict[str, float] = {}
    for name, raw in weights.items():
        ticker = str(name).strip().upper()
        if ticker in normalized:
            raise MarketRiskError(f"duplicate weight for {ticker}")
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise MarketRiskError(f"weight for {ticker} is not a number") from exc
        if not math.isfinite(value):
            raise MarketRiskError(f"weight for {ticker} is not finite")
        normalized[ticker] = value

    ordered = [str(column).strip().upper() for column in columns]
    missing = [ticker for ticker in ordered if ticker not in normalized]
    extra = [ticker for ticker in normalized if ticker not in ordered]
    if missing or extra:
        raise MarketRiskError(
            "weights must match the price columns exactly. "
            f"Missing weights for {missing or 'none'}. "
            f"No price column for {extra or 'none'}."
        )

    total = sum(normalized[ticker] for ticker in ordered)
    if abs(total - 1.0) > 1e-8:
        raise MarketRiskError(f"weights must sum to 1 (got {total:.8f})")
    return pd.Series({ticker: normalized[ticker] for ticker in ordered}, dtype=float)


def simple_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Close-to-close simple returns, R_t = P_t / P_{t-1} - 1.

    The row label is the session on which the return is realized. Simple
    returns, not log returns, are used because a constant-mix portfolio return
    is the weighted sum of asset simple returns.
    """
    if prices.shape[0] < 2:
        raise MarketRiskError("need at least two price dates to compute returns")
    returns = prices.pct_change().iloc[1:]
    array = returns.to_numpy(dtype=float)
    if not np.isfinite(array).all():
        raise MarketRiskError("returns are not finite")
    returns.index.name = "date"
    return returns


def portfolio_returns(asset_returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Constant-mix portfolio simple return, w · R_t, on each session."""
    ordered = asset_returns.loc[:, list(weights.index)]
    portfolio = ordered.mul(weights.to_numpy(dtype=float), axis=1).sum(axis=1)
    portfolio.name = "portfolio"
    portfolio.index.name = "date"
    return portfolio


def portfolio_mean_and_volatility(
    asset_returns: pd.DataFrame,
    weights: pd.Series,
    *,
    zero_mean: bool = False,
) -> tuple[float, float]:
    """Portfolio mean and volatility from the asset covariance matrix.

    Volatility is sqrt(w' Σ w). Σ is the sample covariance with divisor n - 1,
    the same convention as ``Series.std(ddof=1)``. For constant weights this
    matches the sample volatility of the portfolio return series.

    ``zero_mean`` replaces the location with 0 and leaves the covariance
    unchanged. That is the short-horizon "z times sigma" convention.
    """
    if asset_returns.shape[0] < 2:
        raise MarketRiskError("need at least two returns to estimate volatility")
    ordered = asset_returns.loc[:, list(weights.index)]
    weight = weights.to_numpy(dtype=float)
    covariance = ordered.cov(ddof=1).to_numpy(dtype=float)
    variance = float(weight @ covariance @ weight)
    if variance < 0.0:
        if variance > -1e-12:
            variance = 0.0
        else:
            raise MarketRiskError("portfolio variance is negative")
    if zero_mean:
        mean = 0.0
    else:
        mean = float(ordered.mean().to_numpy(dtype=float) @ weight)
    if not math.isfinite(mean) or not math.isfinite(variance):
        raise MarketRiskError("portfolio moments are not finite")
    return mean, math.sqrt(variance)
