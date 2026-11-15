"""Point-in-time estimates, diversification, and the recorded sample."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market_risk.analysis import run_analysis
from market_risk.errors import MarketRiskError
from market_risk.portfolio import portfolio_mean_and_volatility, portfolio_returns, simple_returns
from market_risk.risk import gaussian_var_return, historical_var_return


def _prices_from_returns(returns: pd.DataFrame, start: float = 100.0) -> pd.DataFrame:
    growth = (1.0 + returns).cumprod()
    levels = growth.mul(start)
    seed = pd.DataFrame(
        {column: [start] for column in returns.columns},
        index=[returns.index[0] - pd.offsets.BDay(1)],
    )
    return pd.concat([seed, levels])


def test_point_in_time_window_and_backtest_do_not_share_the_last_return(sample_prices, sample_analysis):
    block = sample_analysis.blocks[0]
    assert block.confidence == pytest.approx(0.95)
    weights = sample_analysis.weights
    portfolio = portfolio_returns(simple_returns(sample_prices), weights)
    window = portfolio.iloc[-sample_analysis.window :]
    preceding = portfolio.iloc[-(sample_analysis.window + 1) : -1]

    assert block.historical.var_return == pytest.approx(historical_var_return(window.to_numpy(), 0.95))
    assert block.historical_backtest.var_returns[-1] == pytest.approx(
        historical_var_return(preceding.to_numpy(), 0.95)
    )
    mean, volatility = portfolio_mean_and_volatility(simple_returns(sample_prices).iloc[-250:], weights)
    assert block.parametric.var_return == pytest.approx(gaussian_var_return(mean, volatility, 0.95))
    assert block.historical.es_return > block.historical.var_return
    assert block.parametric.es_return > block.parametric.var_return


def test_covariance_volatility_matches_the_portfolio_on_the_sample(sample_prices, sample_analysis):
    asset_returns = simple_returns(sample_prices).iloc[-250:]
    portfolio = portfolio_returns(simple_returns(sample_prices), sample_analysis.weights).iloc[-250:]
    _, volatility = portfolio_mean_and_volatility(asset_returns, sample_analysis.weights)
    assert volatility == pytest.approx(float(portfolio.std(ddof=1)), rel=1e-10, abs=1e-12)
    assert sample_analysis.sample_volatility == pytest.approx(volatility)


def test_zero_mean_changes_parametric_var_only(sample_prices):
    full = run_analysis(sample_prices, {"SPY": 0.35, "EFA": 0.20, "EEM": 0.10, "AGG": 0.25, "GLD": 0.10}, confidences=(0.99,), window=250)
    shifted = run_analysis(
        sample_prices,
        {"SPY": 0.35, "EFA": 0.20, "EEM": 0.10, "AGG": 0.25, "GLD": 0.10},
        confidences=(0.99,),
        window=250,
        zero_mean=True,
    )
    assert full.blocks[0].historical.var_return == pytest.approx(shifted.blocks[0].historical.var_return)
    assert shifted.blocks[0].parametric.var_return - full.blocks[0].parametric.var_return == pytest.approx(
        full.sample_mean
    )
    assert shifted.model_mean == pytest.approx(0.0)


def test_a_last_session_shock_does_not_change_past_forecasts():
    index = pd.bdate_range("2022-01-03", periods=29)
    calm = pd.DataFrame({"AAA": [0.001] * 29, "BBB": [0.001] * 29}, index=index)
    prices = _prices_from_returns(calm)
    shocked = prices.copy()
    shocked.iloc[-1, :] = shocked.iloc[-2, :] * 0.5
    weights = {"AAA": 0.5, "BBB": 0.5}

    baseline = run_analysis(prices, weights, confidences=(0.95,), window=10)
    stressed = run_analysis(shocked, weights, confidences=(0.95,), window=10)

    assert stressed.blocks[0].historical.var_return > baseline.blocks[0].historical.var_return
    np.testing.assert_allclose(
        baseline.blocks[0].historical_backtest.var_returns,
        stressed.blocks[0].historical_backtest.var_returns,
    )
    np.testing.assert_allclose(
        baseline.blocks[0].parametric_backtest.var_returns,
        stressed.blocks[0].parametric_backtest.var_returns,
    )
    assert stressed.blocks[0].historical_backtest.hits[-1] == 1
    assert stressed.blocks[0].historical_backtest.realized_returns[-1] < 0.0


def test_offsetting_positions_reduce_portfolio_var():
    index = pd.bdate_range("2023-01-02", periods=40)
    moves = np.array(
        [0.01, -0.02, 0.015, -0.005, 0.0, 0.012, -0.008, 0.004, -0.011, 0.006] * 4
    )
    asset_returns = pd.DataFrame({"AAA": moves, "BBB": -moves}, index=index)
    prices = _prices_from_returns(asset_returns)
    result = run_analysis(
        prices,
        {"AAA": 0.5, "BBB": 0.5},
        confidences=(0.95,),
        window=20,
        zero_mean=True,
    )
    block = result.blocks[0]
    # Price reconstruction leaves a numerical residue. It is far below a real loss.
    assert block.parametric.var_return == pytest.approx(0.0, abs=1e-8)
    assert block.historical.var_return == pytest.approx(0.0, abs=1e-8)
    assert block.parametric_standalone.total > 1e-3
    assert block.historical_standalone.total > 1e-3


def test_perfectly_correlated_book_has_no_parametric_diversification():
    index = pd.bdate_range("2023-01-02", periods=30)
    moves = np.linspace(-0.02, 0.03, 30)
    asset_returns = pd.DataFrame({"AAA": moves, "BBB": moves}, index=index)
    prices = _prices_from_returns(asset_returns)
    result = run_analysis(
        prices,
        {"AAA": 0.4, "BBB": 0.6},
        confidences=(0.95,),
        window=20,
        zero_mean=True,
    )
    block = result.blocks[0]
    assert block.parametric_standalone.total == pytest.approx(block.parametric.var_return, abs=1e-12)


def test_single_asset_standalone_equals_portfolio_var():
    index = pd.bdate_range("2023-01-02", periods=30)
    asset_returns = pd.DataFrame(
        {"AAA": np.linspace(-0.03, 0.02, 30)},
        index=index,
    )
    prices = _prices_from_returns(asset_returns)
    result = run_analysis(prices, {"AAA": 1.0}, confidences=(0.95,), window=20)
    block = result.blocks[0]
    assert float(block.historical_standalone.by_asset["AAA"]) == pytest.approx(block.historical.var_return)
    assert float(block.parametric_standalone.by_asset["AAA"]) == pytest.approx(block.parametric.var_return)


def test_analysis_rejects_a_short_history_and_duplicate_confidence():
    index = pd.bdate_range("2024-01-01", periods=5)
    prices = pd.DataFrame({"AAA": [10, 11, 12, 11, 13]}, index=index, dtype=float)
    with pytest.raises(MarketRiskError, match="backtest"):
        run_analysis(prices, {"AAA": 1.0}, window=10)
    longer = pd.DataFrame(
        {"AAA": np.linspace(10, 20, 20)},
        index=pd.bdate_range("2024-01-01", periods=20),
    )
    with pytest.raises(MarketRiskError, match="unique"):
        run_analysis(longer, {"AAA": 1.0}, confidences=(0.95, 0.95), window=10)
