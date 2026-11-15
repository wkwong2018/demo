"""One-day historical and Gaussian VaR and Expected Shortfall.

Losses are positive. A VaR of 0.02 is a 2% loss threshold. A negative VaR
means the threshold outcome is a gain.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike
from scipy.stats import norm

from market_risk.errors import MarketRiskError
from market_risk.validation import as_1d_float, validate_confidence


def historical_var_return(returns: ArrayLike, confidence: float) -> float:
    """Historical-simulation VaR as a positive loss fraction.

    VaR_c = -Q_{1-c}(R), where Q is the Hyndman-Fan type 7 sample quantile
    (NumPy's linear quantile). The sample is equally weighted. There is no
    volatility scaling and no exponential decay.
    """
    sample = as_1d_float(returns, name="returns")
    level = validate_confidence(confidence)
    quantile = float(np.quantile(sample, 1.0 - level, method="linear"))
    return -quantile


def historical_es_return(returns: ArrayLike, confidence: float) -> float:
    """Historical Expected Shortfall as a positive loss fraction.

    This is Acerbi's estimator on the empirical distribution. With ordered
    returns R_(1) <= ... <= R_(n), alpha = 1 - c, u = n * alpha, and
    k = floor(u):

        ES_c = -1/u * (sum_{i=1}^{k} R_(i) + (u - k) * R_(k+1))

    When u is an integer the second term drops out and ES is the average of
    the worst u returns, sign-flipped into a loss. Values of u that land on
    an integer up to binary rounding error are treated as that integer.
    """
    sample = as_1d_float(returns, name="returns")
    level = validate_confidence(confidence)
    ordered = np.sort(sample)
    n = int(ordered.size)
    mass = _tail_mass(n, level)
    if mass >= n:
        return -float(np.mean(ordered))

    k = int(math.floor(mass))
    fraction = mass - k
    if fraction <= 1e-12:
        if k == 0:
            raise MarketRiskError("tail probability is too small for this sample")
        return -float(np.mean(ordered[:k]))

    tail = float(ordered[:k].sum()) + fraction * float(ordered[k])
    return -tail / mass


def gaussian_var_return(mean: float, volatility: float, confidence: float) -> float:
    """Gaussian VaR as a positive loss fraction.

    VaR_c = -(mean + volatility * invPhi(1 - c)).
    """
    location, scale, level = _gaussian_arguments(mean, volatility, confidence)
    z_alpha = float(norm.ppf(1.0 - level))
    return -(location + scale * z_alpha)


def gaussian_es_return(mean: float, volatility: float, confidence: float) -> float:
    """Gaussian Expected Shortfall as a positive loss fraction.

    ES_c = -mean + volatility * phi(invPhi(1 - c)) / (1 - c).

    This is -E[R | R <= q], the mean loss beyond the Gaussian quantile.
    """
    location, scale, level = _gaussian_arguments(mean, volatility, confidence)
    alpha = 1.0 - level
    z_alpha = float(norm.ppf(alpha))
    return -location + scale * float(norm.pdf(z_alpha)) / alpha


def sample_mean_and_volatility(
    returns: ArrayLike,
    *,
    zero_mean: bool = False,
) -> tuple[float, float]:
    """Sample mean and sample volatility (divisor n - 1) of a return series."""
    sample = as_1d_float(returns, name="returns")
    mean = 0.0 if zero_mean else float(np.mean(sample))
    volatility = float(np.std(sample, ddof=1))
    if not math.isfinite(mean) or not math.isfinite(volatility) or volatility < 0.0:
        raise MarketRiskError("sample moments are not finite")
    return mean, volatility


def parametric_var_return(
    returns: ArrayLike,
    confidence: float,
    *,
    zero_mean: bool = False,
) -> float:
    """Gaussian VaR from the sample mean and sample volatility of ``returns``."""
    mean, volatility = sample_mean_and_volatility(returns, zero_mean=zero_mean)
    return gaussian_var_return(mean, volatility, confidence)


def parametric_es_return(
    returns: ArrayLike,
    confidence: float,
    *,
    zero_mean: bool = False,
) -> float:
    """Gaussian ES from the sample mean and sample volatility of ``returns``."""
    mean, volatility = sample_mean_and_volatility(returns, zero_mean=zero_mean)
    return gaussian_es_return(mean, volatility, confidence)


def _gaussian_arguments(
    mean: float,
    volatility: float,
    confidence: float,
) -> tuple[float, float, float]:
    try:
        location = float(mean)
        scale = float(volatility)
    except (TypeError, ValueError) as exc:
        raise MarketRiskError("mean and volatility must be numbers") from exc
    if not math.isfinite(location) or not math.isfinite(scale) or scale < 0.0:
        raise MarketRiskError("volatility must be finite and non-negative")
    return location, scale, validate_confidence(confidence)


def _tail_mass(n: int, confidence: float) -> float:
    """Return n * (1 - confidence), snapping ulp-sized misses off integers."""
    mass = n * (1.0 - confidence)
    nearest = round(mass)
    tolerance = 1e-8 * max(n, 1)
    if abs(mass - nearest) <= tolerance:
        mass = float(nearest)
    if mass <= 0.0:
        raise MarketRiskError(
            "tail probability is too small for this sample; "
            "lower the confidence or lengthen the window"
        )
    if mass > n:
        return float(n)
    return mass
