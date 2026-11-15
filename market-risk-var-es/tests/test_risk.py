"""Closed forms and hand-computed historical VaR and ES."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import norm

from market_risk.errors import MarketRiskError
from market_risk.risk import (
    gaussian_es_return,
    gaussian_var_return,
    historical_es_return,
    historical_var_return,
    parametric_es_return,
    parametric_var_return,
)


def test_historical_var_uses_the_type7_quantile():
    # n = 5, alpha = 0.20. Linear quantile position = (5 - 1) * 0.20 = 0.80.
    # Q = -0.04 + 0.80 * (-0.01 - -0.04) = -0.016, so VaR = 0.016.
    returns = np.array([-0.04, -0.01, 0.0, 0.02, 0.03])
    assert historical_var_return(returns, 0.80) == pytest.approx(0.016)


def test_historical_es_integer_and_fractional_tails():
    returns = np.array([0.05, -0.10, 0.12, -0.04, 0.0, 0.08, -0.01, 0.02, 0.10, 0.03])
    # 80% ES, alpha = 0.20, u = 2. Average of the two worst returns, as a loss.
    assert historical_es_return(returns, 0.80) == pytest.approx(0.07)

    fractional = np.array([-0.10, -0.04, -0.01, 0.0, 0.02, 0.03, 0.05, 0.08, 0.10, 0.12])
    # 75% ES, alpha = 0.25, u = 2.5.
    # -(1 / 2.5) * (-0.10 + -0.04 + 0.5 * -0.01) = 0.058.
    assert historical_es_return(fractional, 0.75) == pytest.approx(0.058)


def test_historical_es_snaps_a_binary_rounding_miss_to_the_integer_tail():
    # 1 - 0.8 is not exactly 0.2, so 5 * (1 - 0.8) is just under 1.
    # The estimator treats that as one tail point: the worst return.
    returns = np.array([-0.04, -0.01, 0.0, 0.02, 0.03])
    assert historical_es_return(returns, 0.8) == pytest.approx(0.04)


def test_flat_sample_var_and_es_are_the_signed_return():
    returns = np.array([0.01, 0.01, 0.01, 0.01])
    assert historical_var_return(returns, 0.99) == pytest.approx(-0.01)
    assert historical_es_return(returns, 0.99) == pytest.approx(-0.01)
    assert parametric_var_return(returns, 0.99) == pytest.approx(-0.01)
    assert parametric_es_return(returns, 0.99) == pytest.approx(-0.01)


def test_standard_normal_var_and_es_match_published_constants():
    assert gaussian_var_return(0.0, 1.0, 0.95) == pytest.approx(1.6448536269514722)
    assert gaussian_es_return(0.0, 1.0, 0.95) == pytest.approx(2.0627128075074257)
    assert gaussian_var_return(0.0, 1.0, 0.99) == pytest.approx(2.3263478740408408)
    assert gaussian_es_return(0.0, 1.0, 0.99) == pytest.approx(2.665214220345806)


def test_gaussian_es_matches_the_truncated_expectation():
    mean, volatility, confidence = 0.0004, 0.012, 0.99
    alpha = 1.0 - confidence
    cutoff = float(norm.ppf(alpha, loc=mean, scale=volatility))
    tail_mean = float(
        norm.expect(
            lambda value: value,
            loc=mean,
            scale=volatility,
            lb=-np.inf,
            ub=cutoff,
            conditional=True,
        )
    )
    assert gaussian_var_return(mean, volatility, confidence) == pytest.approx(-cutoff)
    assert gaussian_es_return(mean, volatility, confidence) == pytest.approx(-tail_mean, rel=1e-9)


@pytest.mark.parametrize("confidence", [0.90, 0.95, 0.975, 0.99, 0.995])
def test_gaussian_es_exceeds_gaussian_var(confidence):
    var = gaussian_var_return(0.0002, 0.01, confidence)
    es = gaussian_es_return(0.0002, 0.01, confidence)
    assert es > var > 0.0


def test_zero_mean_shifts_parametric_var_by_the_sample_mean():
    returns = np.array([0.02, 0.01, 0.03, 0.015, 0.025, 0.018])
    with_mean = parametric_var_return(returns, 0.95, zero_mean=False)
    at_zero = parametric_var_return(returns, 0.95, zero_mean=True)
    assert at_zero - with_mean == pytest.approx(float(np.mean(returns)))
    assert parametric_es_return(returns, 0.95, zero_mean=True) - parametric_es_return(
        returns, 0.95, zero_mean=False
    ) == pytest.approx(float(np.mean(returns)))


def test_historical_var_is_close_to_gaussian_var_on_a_normal_sample():
    sample = np.random.default_rng(42).normal(0.0005, 0.01, size=200_000)
    historical = historical_var_return(sample, 0.99)
    parametric = parametric_var_return(sample, 0.99)
    assert historical == pytest.approx(parametric, rel=0.02, abs=0.0005)


def test_risk_measures_reject_bad_inputs():
    with pytest.raises(MarketRiskError):
        historical_var_return(np.array([0.01]), 0.95)
    with pytest.raises(MarketRiskError):
        historical_es_return(np.array([0.01, np.nan]), 0.95)
    with pytest.raises(MarketRiskError):
        gaussian_var_return(0.0, 0.01, 1.5)
    with pytest.raises(MarketRiskError):
        gaussian_es_return(0.0, -0.01, 0.95)
    with pytest.raises(MarketRiskError):
        parametric_var_return(np.array([[0.01, 0.02], [0.03, 0.04]]), 0.95)
