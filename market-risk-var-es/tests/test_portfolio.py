"""Prices, weights, and portfolio aggregation."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from market_risk.errors import MarketRiskError
from market_risk.portfolio import (
    align_weights,
    load_prices,
    portfolio_mean_and_volatility,
    portfolio_returns,
    simple_returns,
)


def test_load_prices_sorts_dates_and_uppercases_tickers(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text(
        "date,spy,efa\n2020-01-03,101,50\n2020-01-02,100,40\n",
        encoding="utf-8",
    )
    prices = load_prices(path)
    assert list(prices.columns) == ["SPY", "EFA"]
    assert list(prices.index) == [pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-03")]
    assert prices.loc["2020-01-02", "SPY"] == pytest.approx(100)


def test_load_prices_rejects_bad_files(tmp_path):
    missing = tmp_path / "missing.csv"
    with pytest.raises(MarketRiskError, match="not found"):
        load_prices(missing)

    duplicate_dates = tmp_path / "dup.csv"
    duplicate_dates.write_text("date,AAA\n2020-01-02,10\n2020-01-02,11\n", encoding="utf-8")
    with pytest.raises(MarketRiskError, match="duplicate dates"):
        load_prices(duplicate_dates)

    negative = tmp_path / "neg.csv"
    negative.write_text("date,AAA\n2020-01-02,10\n2020-01-03,-1\n", encoding="utf-8")
    with pytest.raises(MarketRiskError, match="positive"):
        load_prices(negative)

    broken_date = tmp_path / "date.csv"
    broken_date.write_text("date,AAA\nnot-a-date,10\n2020-01-03,11\n", encoding="utf-8")
    with pytest.raises(MarketRiskError, match="date"):
        load_prices(broken_date)


def test_weights_must_match_columns_and_sum_to_one():
    columns = ["SPY", "AGG"]
    with pytest.raises(MarketRiskError, match="sum to 1"):
        align_weights(columns, {"SPY": 0.4, "AGG": 0.4})
    with pytest.raises(MarketRiskError, match="Missing weights"):
        align_weights(columns, {"SPY": 1.0})
    with pytest.raises(MarketRiskError, match="No price column"):
        align_weights(columns, {"SPY": 0.5, "AGG": 0.5, "GLD": 0.0})

    short = align_weights(columns, {"spy": 1.5, "agg": -0.5})
    assert short["SPY"] == pytest.approx(1.5)
    assert short["AGG"] == pytest.approx(-0.5)


def test_portfolio_return_is_the_weighted_sum_of_simple_returns():
    prices = pd.DataFrame(
        {"AAA": [100.0, 110.0, 99.0], "BBB": [50.0, 50.0, 55.0]},
        index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
    )
    weights = align_weights(prices.columns, {"AAA": 0.25, "BBB": 0.75})
    asset_returns = simple_returns(prices)
    portfolio = portfolio_returns(asset_returns, weights)

    assert asset_returns.loc["2020-01-03", "AAA"] == pytest.approx(0.10)
    assert asset_returns.loc["2020-01-03", "BBB"] == pytest.approx(0.0)
    assert portfolio.loc["2020-01-03"] == pytest.approx(0.25 * 0.10 + 0.75 * 0.0)
    assert portfolio.loc["2020-01-06"] == pytest.approx(0.25 * (99 / 110 - 1) + 0.75 * (55 / 50 - 1))


def test_covariance_volatility_matches_the_portfolio_series():
    asset_returns = pd.DataFrame(
        {
            "AAA": [0.01, -0.02, 0.03, 0.00],
            "BBB": [0.02, 0.00, -0.01, 0.01],
        },
        index=pd.bdate_range("2024-01-01", periods=4),
    )
    weights = align_weights(asset_returns.columns, {"AAA": 0.25, "BBB": 0.75})
    portfolio = portfolio_returns(asset_returns, weights)
    values = [float(value) for value in portfolio.to_list()]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)

    estimated_mean, estimated_vol = portfolio_mean_and_volatility(asset_returns, weights)
    assert estimated_mean == pytest.approx(mean)
    assert estimated_vol == pytest.approx(math.sqrt(variance))

    zero_mean, zero_vol = portfolio_mean_and_volatility(
        asset_returns, weights, zero_mean=True
    )
    assert zero_mean == pytest.approx(0.0)
    assert zero_vol == pytest.approx(estimated_vol)


def test_sample_fixture_covers_the_recorded_span(sample_prices):
    assert list(sample_prices.columns) == ["SPY", "EFA", "EEM", "AGG", "GLD"]
    assert sample_prices.index[0] == pd.Timestamp("2016-01-04")
    assert sample_prices.index[-1] == pd.Timestamp("2026-10-30")
    assert len(sample_prices) == 2723
    assert sample_prices.loc["2020-02-19", "SPY"] > sample_prices.loc["2020-03-23", "SPY"]
    assert np.isfinite(sample_prices.to_numpy()).all()
