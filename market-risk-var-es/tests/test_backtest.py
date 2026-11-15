"""Kupiec and Christoffersen tests, including hand-computed likelihood ratios."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import chi2

from market_risk.backtest import (
    christoffersen_conditional_coverage,
    christoffersen_independence,
    kupiec_unconditional_coverage,
    rolling_var_backtest,
    transition_counts,
)
from market_risk.errors import MarketRiskError
from market_risk.risk import historical_var_return


def test_kupiec_perfect_coverage_has_a_zero_statistic():
    hits = np.array([1] * 5 + [0] * 95)
    result = kupiec_unconditional_coverage(hits, alpha=0.05, significance=0.05)
    assert result.statistic == pytest.approx(0.0, abs=1e-12)
    assert result.p_value == pytest.approx(1.0)
    assert result.degrees_of_freedom == 1
    assert result.rejected is False


def test_kupiec_matches_a_hand_computed_likelihood_ratio():
    # 10 exceptions in 100 sessions, model tail 5%.
    hits = np.array([1] * 10 + [0] * 90)
    result = kupiec_unconditional_coverage(hits, alpha=0.05, significance=0.05)
    assert result.statistic == pytest.approx(4.130843782549277)
    assert result.p_value == pytest.approx(0.042108350096184785)
    assert result.rejected is True


def test_kupiec_zero_exceptions_is_finite_and_rejects_a_long_sample():
    hits = np.zeros(500, dtype=int)
    result = kupiec_unconditional_coverage(hits, alpha=0.05, significance=0.05)
    assert math.isfinite(result.statistic)
    assert result.statistic > 0.0
    assert result.rejected is True


def test_christoffersen_independence_matches_a_hand_computed_ratio():
    # Transitions: 00, 01, 11, 11, 10, 00, 00.
    # n00=3, n01=1, n10=1, n11=2.
    hits = np.array([0, 0, 1, 1, 1, 0, 0, 0])
    counts = transition_counts(hits)
    assert (counts.n00, counts.n01, counts.n10, counts.n11) == (3, 1, 1, 2)
    assert counts.pi01 == pytest.approx(0.25)
    assert counts.pi11 == pytest.approx(2 / 3)
    result = christoffersen_independence(hits, significance=0.05)
    assert result.statistic == pytest.approx(1.2429472990872608)
    assert result.p_value == pytest.approx(0.2649037925655114)
    assert result.rejected is False


def test_independence_is_zero_when_a_state_never_occurs():
    hits = np.zeros(20, dtype=int)
    result = christoffersen_independence(hits)
    assert transition_counts(hits).pi11 is None
    assert result.statistic == pytest.approx(0.0, abs=1e-12)
    assert result.rejected is False


def test_conditional_coverage_adds_the_two_statistics():
    hits = np.array([0, 0, 1, 1, 1, 0, 0, 0, 1, 0])
    coverage = kupiec_unconditional_coverage(hits, alpha=0.05)
    independence = christoffersen_independence(hits)
    conditional = christoffersen_conditional_coverage(hits, alpha=0.05)
    assert conditional.statistic == pytest.approx(coverage.statistic + independence.statistic)
    assert conditional.degrees_of_freedom == 2
    assert conditional.p_value == pytest.approx(float(chi2.sf(conditional.statistic, 2)))


def test_clustered_exceptions_reject_independence():
    hits = np.array([1] * 40 + [0] * 200 + [1] * 40 + [0] * 200)
    counts = transition_counts(hits)
    assert counts.pi11 is not None and counts.pi01 is not None
    assert counts.pi11 > counts.pi01
    result = christoffersen_independence(hits, significance=0.05)
    assert result.rejected is True


def test_hits_must_be_binary_and_independence_needs_two_observations():
    with pytest.raises(MarketRiskError):
        kupiec_unconditional_coverage(np.array([0, 2, 1]), alpha=0.05)
    with pytest.raises(MarketRiskError):
        christoffersen_independence(np.array([1]))
    with pytest.raises(MarketRiskError):
        kupiec_unconditional_coverage(np.array([0, 0, 1]), alpha=0.0)


def test_exception_uses_a_strict_exceedance():
    index = pd.bdate_range("2021-01-01", periods=12)
    flat = pd.Series([-0.01] * 12, index=index)
    quiet = rolling_var_backtest(
        flat,
        confidence=0.95,
        window=10,
        method="historical",
        significance=0.05,
    )
    assert quiet.hits.sum() == 0

    breached = flat.copy()
    breached.iloc[-1] = -0.02
    scored = rolling_var_backtest(
        breached,
        confidence=0.95,
        window=10,
        method="historical",
        significance=0.05,
    )
    assert scored.hits[0] == 0
    assert scored.hits[-1] == 1
    assert scored.var_returns[-1] == pytest.approx(0.01)


def test_rolling_forecast_ignores_later_returns():
    rng = np.random.default_rng(7)
    index = pd.bdate_range("2020-01-01", periods=80)
    series = pd.Series(rng.normal(0.0, 0.01, size=80), index=index)
    original = rolling_var_backtest(
        series,
        confidence=0.95,
        window=20,
        method="historical",
        significance=0.05,
    )
    corrupted = series.copy()
    corrupted.iloc[50:] = 0.2
    shocked = rolling_var_backtest(
        corrupted,
        confidence=0.95,
        window=20,
        method="parametric",
        significance=0.05,
    )
    historical = rolling_var_backtest(
        corrupted,
        confidence=0.95,
        window=20,
        method="historical",
        significance=0.05,
    )
    # Session 50 is forecast from returns [30, 50), so the first 31 forecasts
    # (sessions 20 through 50 inclusive) are unchanged.
    np.testing.assert_allclose(original.var_returns[:31], historical.var_returns[:31])
    assert not np.allclose(original.var_returns[40:], historical.var_returns[40:])
    # The parametric call is a separate method; it still has to be a finite forecast.
    assert np.isfinite(shocked.var_returns).all()
    manual = historical_var_return(series.iloc[10:30].to_numpy(), 0.95)
    assert original.var_returns[10] == pytest.approx(manual)


def test_unknown_method_and_short_sample_are_rejected():
    series = pd.Series([0.01, -0.01, 0.02], index=pd.bdate_range("2024-01-01", periods=3))
    with pytest.raises(MarketRiskError, match="window"):
        rolling_var_backtest(
            series,
            confidence=0.95,
            window=2,
            method="historical",
            significance=0.05,
        )
    long_enough = pd.Series(np.linspace(-0.02, 0.02, 12), index=pd.bdate_range("2024-01-01", periods=12))
    with pytest.raises(MarketRiskError, match="method"):
        rolling_var_backtest(
            long_enough,
            confidence=0.95,
            window=5,
            method="garch",
            significance=0.05,
        )
