"""Point-in-time risk and a rolling backtest for one portfolio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from market_risk.backtest import VarBacktest, rolling_var_backtest
from market_risk.errors import MarketRiskError
from market_risk.portfolio import (
    TRADING_DAYS_PER_YEAR,
    align_weights,
    portfolio_mean_and_volatility,
    portfolio_returns,
    simple_returns,
)
from market_risk.risk import (
    gaussian_es_return,
    gaussian_var_return,
    historical_es_return,
    historical_var_return,
    sample_mean_and_volatility,
)
from market_risk.validation import validate_confidences, validate_portfolio_value, validate_significance
from market_risk.version import __version__


@dataclass(frozen=True)
class TailRisk:
    """VaR and Expected Shortfall as positive loss fractions of portfolio value."""

    method: str
    var_return: float
    es_return: float


@dataclass(frozen=True, eq=False)
class StandaloneVar:
    """VaR of each weighted position held on its own.

    These numbers are not an Euler allocation and they do not sum to the
    portfolio VaR. The gap is a description of offsetting moves.
    """

    method: str
    by_asset: pd.Series

    @property
    def total(self) -> float:
        return float(self.by_asset.sum())


@dataclass(frozen=True, eq=False)
class ConfidenceResult:
    """Risk and backtests at one confidence level."""

    confidence: float
    historical: TailRisk
    parametric: TailRisk
    historical_standalone: StandaloneVar
    parametric_standalone: StandaloneVar
    historical_backtest: VarBacktest
    parametric_backtest: VarBacktest


@dataclass(frozen=True, eq=False)
class AnalysisResult:
    """Everything the report prints."""

    version: str
    portfolio_value: float
    weights: pd.Series
    zero_mean: bool
    window: int
    significance: float
    price_start: pd.Timestamp
    price_end: pd.Timestamp
    price_rows: int
    return_rows: int
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    sample_mean: float
    sample_volatility: float
    model_mean: float
    asset_volatility: pd.Series
    correlation: pd.DataFrame
    blocks: tuple[ConfidenceResult, ...]

    @property
    def annualized_volatility(self) -> float:
        """sqrt(252) scaling of the estimation-window volatility, for description only."""
        return self.sample_volatility * (TRADING_DAYS_PER_YEAR ** 0.5)


def run_analysis(
    prices: pd.DataFrame,
    weights: Mapping[str, float],
    *,
    portfolio_value: float = 1_000_000.0,
    confidences: Sequence[float] = (0.95, 0.99),
    window: int = 250,
    zero_mean: bool = False,
    significance: float = 0.05,
) -> AnalysisResult:
    """Estimate current 1-day risk and backtest rolling forecasts.

    The current estimate uses the last ``window`` realized returns and is the
    risk number for the next session. Each backtest forecast for session t
    uses only the preceding ``window`` returns.
    """
    levels = validate_confidences(confidences)
    size = validate_significance(significance)
    value = validate_portfolio_value(portfolio_value)
    if window < 2:
        raise MarketRiskError("window must be at least 2 returns")

    aligned = align_weights(prices.columns, weights)
    asset_returns = simple_returns(prices)
    portfolio = portfolio_returns(asset_returns, aligned)
    if portfolio.size < window + 2:
        raise MarketRiskError(
            "the backtest needs at least "
            f"{window + 2} returns for window={window} (got {portfolio.size})"
        )

    window_asset = asset_returns.iloc[-window:]
    window_portfolio = portfolio.iloc[-window:]
    sample_mean, sample_volatility = portfolio_mean_and_volatility(
        window_asset,
        aligned,
        zero_mean=False,
    )
    model_mean = 0.0 if zero_mean else sample_mean
    blocks = tuple(
        _confidence_block(
            confidence=level,
            window_asset=window_asset,
            window_portfolio=window_portfolio.to_numpy(dtype=float),
            portfolio=portfolio,
            weights=aligned,
            model_mean=model_mean,
            model_volatility=sample_volatility,
            window=window,
            zero_mean=zero_mean,
            significance=size,
        )
        for level in levels
    )
    return AnalysisResult(
        version=__version__,
        portfolio_value=value,
        weights=aligned,
        zero_mean=zero_mean,
        window=window,
        significance=size,
        price_start=pd.Timestamp(prices.index[0]),
        price_end=pd.Timestamp(prices.index[-1]),
        price_rows=int(prices.shape[0]),
        return_rows=int(portfolio.size),
        window_start=pd.Timestamp(window_portfolio.index[0]),
        window_end=pd.Timestamp(window_portfolio.index[-1]),
        sample_mean=sample_mean,
        sample_volatility=sample_volatility,
        model_mean=model_mean,
        asset_volatility=window_asset.std(ddof=1),
        correlation=window_asset.corr(),
        blocks=blocks,
    )


def _confidence_block(
    *,
    confidence: float,
    window_asset: pd.DataFrame,
    window_portfolio: np.ndarray,
    portfolio: pd.Series,
    weights: pd.Series,
    model_mean: float,
    model_volatility: float,
    window: int,
    zero_mean: bool,
    significance: float,
) -> ConfidenceResult:
    historical = TailRisk(
        method="historical",
        var_return=historical_var_return(window_portfolio, confidence),
        es_return=historical_es_return(window_portfolio, confidence),
    )
    parametric = TailRisk(
        method="parametric",
        var_return=gaussian_var_return(model_mean, model_volatility, confidence),
        es_return=gaussian_es_return(model_mean, model_volatility, confidence),
    )
    return ConfidenceResult(
        confidence=confidence,
        historical=historical,
        parametric=parametric,
        historical_standalone=_standalone(
            window_asset, weights, confidence, method="historical", zero_mean=zero_mean
        ),
        parametric_standalone=_standalone(
            window_asset, weights, confidence, method="parametric", zero_mean=zero_mean
        ),
        historical_backtest=rolling_var_backtest(
            portfolio,
            confidence=confidence,
            window=window,
            method="historical",
            zero_mean=zero_mean,
            significance=significance,
        ),
        parametric_backtest=rolling_var_backtest(
            portfolio,
            confidence=confidence,
            window=window,
            method="parametric",
            zero_mean=zero_mean,
            significance=significance,
        ),
    )


def _standalone(
    asset_returns: pd.DataFrame,
    weights: pd.Series,
    confidence: float,
    *,
    method: str,
    zero_mean: bool,
) -> StandaloneVar:
    values: dict[str, float] = {}
    for ticker, weight in weights.items():
        position = asset_returns[ticker].to_numpy(dtype=float) * float(weight)
        if method == "historical":
            values[ticker] = historical_var_return(position, confidence)
        else:
            mean, volatility = sample_mean_and_volatility(position, zero_mean=zero_mean)
            values[ticker] = gaussian_var_return(mean, volatility, confidence)
    return StandaloneVar(method=method, by_asset=pd.Series(values, dtype=float))
