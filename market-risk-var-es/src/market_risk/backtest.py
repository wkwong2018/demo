"""VaR exception backtests.

An exception (a hit) on session t occurs when the realized simple return is
strictly less than minus the VaR that was forecast from earlier sessions.
Ties are not exceptions.

The tests are the Kupiec (1995) unconditional coverage test and the
Christoffersen (1998) independence and conditional coverage tests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike
from scipy.stats import chi2

from market_risk.errors import MarketRiskError
from market_risk.risk import historical_var_return, sample_mean_and_volatility, gaussian_var_return
from market_risk.validation import as_hits, validate_confidence, validate_significance


@dataclass(frozen=True)
class HypothesisTest:
    """One likelihood-ratio test against a chi-square reference distribution."""

    name: str
    null_hypothesis: str
    statistic: float
    p_value: float
    degrees_of_freedom: int
    significance: float

    @property
    def rejected(self) -> bool:
        """True when the p-value is below the test size."""
        return bool(self.p_value < self.significance)


@dataclass(frozen=True)
class TransitionCounts:
    """First-order hit transitions. A hit is state 1."""

    n00: int
    n01: int
    n10: int
    n11: int

    @property
    def n_transitions(self) -> int:
        return self.n00 + self.n01 + self.n10 + self.n11

    @property
    def pi(self) -> float:
        """Unconditional frequency of hits among the transitions."""
        return (self.n01 + self.n11) / self.n_transitions

    @property
    def pi01(self) -> float | None:
        """P(hit today | no hit yesterday). None when that state never occurs."""
        denominator = self.n00 + self.n01
        if denominator == 0:
            return None
        return self.n01 / denominator

    @property
    def pi11(self) -> float | None:
        """P(hit today | hit yesterday). None when that state never occurs."""
        denominator = self.n10 + self.n11
        if denominator == 0:
            return None
        return self.n11 / denominator


@dataclass(frozen=True, eq=False)
class VarBacktest:
    """Rolling one-day VaR forecasts and the three coverage tests."""

    method: str
    confidence: float
    alpha: float
    window: int
    zero_mean: bool
    dates: pd.DatetimeIndex
    realized_returns: np.ndarray
    var_returns: np.ndarray
    hits: np.ndarray
    transitions: TransitionCounts
    kupiec: HypothesisTest
    independence: HypothesisTest
    conditional: HypothesisTest

    @property
    def observations(self) -> int:
        return int(self.hits.size)

    @property
    def exceptions(self) -> int:
        return int(self.hits.sum())

    @property
    def exception_rate(self) -> float:
        return self.exceptions / self.observations

    @property
    def expected_exceptions(self) -> float:
        return self.alpha * self.observations


def transition_counts(hits: ArrayLike) -> TransitionCounts:
    """Count 0/1 transitions. At least two hit observations are required."""
    series = as_hits(hits)
    if series.size < 2:
        raise MarketRiskError("independence needs at least two hit observations")
    previous = series[:-1]
    current = series[1:]
    return TransitionCounts(
        n00=int(np.sum((previous == 0) & (current == 0))),
        n01=int(np.sum((previous == 0) & (current == 1))),
        n10=int(np.sum((previous == 1) & (current == 0))),
        n11=int(np.sum((previous == 1) & (current == 1))),
    )


def kupiec_unconditional_coverage(
    hits: ArrayLike,
    alpha: float,
    significance: float = 0.05,
) -> HypothesisTest:
    """Kupiec proportion-of-failures test.

    H0: the exception rate equals ``alpha`` (the model tail probability).
    LR_uc = -2 ln(L(alpha) / L(p_hat)) is referred to chi-square with 1 df.
    ``0 * ln(0)`` is taken as 0, so a sample with no exceptions still has a
    finite statistic.
    """
    series = as_hits(hits)
    tail = _validate_alpha(alpha)
    size = validate_significance(significance)
    successes = int(series.sum())
    trials = int(series.size)
    p_hat = successes / trials
    statistic = _likelihood_ratio(
        _binomial_loglik(successes, trials, tail),
        _binomial_loglik(successes, trials, p_hat),
    )
    return HypothesisTest(
        name="Kupiec unconditional coverage",
        null_hypothesis="the exception rate equals the model tail probability",
        statistic=statistic,
        p_value=_chi2_survival(statistic, 1),
        degrees_of_freedom=1,
        significance=size,
    )


def christoffersen_independence(
    hits: ArrayLike,
    significance: float = 0.05,
) -> HypothesisTest:
    """Christoffersen first-order Markov independence test.

    H0: today's hit probability does not depend on yesterday's hit.
    The unrestricted model has two probabilities, pi01 and pi11. The
    restricted model has one probability, pi. A state that never occurs is
    left out of both likelihoods, so a sample with no hits has LR_ind = 0.
    """
    counts = transition_counts(hits)
    size = validate_significance(significance)
    hit_transitions = counts.n01 + counts.n11
    quiet_transitions = counts.n00 + counts.n10
    restricted = _binomial_loglik(hit_transitions, counts.n_transitions, counts.pi)

    unrestricted = 0.0
    if counts.pi01 is not None:
        unrestricted += _binomial_loglik(counts.n01, counts.n00 + counts.n01, counts.pi01)
    if counts.pi11 is not None:
        unrestricted += _binomial_loglik(counts.n11, counts.n10 + counts.n11, counts.pi11)

    statistic = _likelihood_ratio(restricted, unrestricted)
    return HypothesisTest(
        name="Christoffersen independence",
        null_hypothesis="exceptions are independent over time",
        statistic=statistic,
        p_value=_chi2_survival(statistic, 1),
        degrees_of_freedom=1,
        significance=size,
    )


def christoffersen_conditional_coverage(
    hits: ArrayLike,
    alpha: float,
    significance: float = 0.05,
) -> HypothesisTest:
    """Christoffersen conditional coverage test.

    LR_cc = LR_uc + LR_ind, referred to chi-square with 2 degrees of freedom.
    Coverage uses every hit. Independence uses the n - 1 transitions. That is
    the original decomposition.
    """
    coverage = kupiec_unconditional_coverage(hits, alpha, significance)
    independence = christoffersen_independence(hits, significance)
    statistic = coverage.statistic + independence.statistic
    return HypothesisTest(
        name="Christoffersen conditional coverage",
        null_hypothesis="coverage is correct and exceptions are independent",
        statistic=statistic,
        p_value=_chi2_survival(statistic, 2),
        degrees_of_freedom=2,
        significance=coverage.significance,
    )


def rolling_var_backtest(
    returns: pd.Series,
    *,
    confidence: float,
    window: int,
    method: str,
    zero_mean: bool = False,
    significance: float = 0.05,
) -> VarBacktest:
    """Forecast one-day VaR from a rolling window and score the next session.

    The forecast for session t uses returns[t - window : t] and does not see
    the return on t. ``method`` is ``historical`` or ``parametric``.
    """
    if method not in {"historical", "parametric"}:
        raise MarketRiskError("method must be 'historical' or 'parametric'")
    if not isinstance(returns, pd.Series):
        raise MarketRiskError("returns must be a pandas Series indexed by date")
    level = validate_confidence(confidence)
    if window < 2:
        raise MarketRiskError("window must be at least 2 returns")

    values = returns.to_numpy(dtype=float)
    if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
        raise MarketRiskError("returns must be a finite one-dimensional series")
    if values.size < window + 2:
        raise MarketRiskError(
            "the backtest needs at least "
            f"{window + 2} returns for window={window} (got {values.size})"
        )

    forecasts = np.empty(values.size - window, dtype=float)
    for offset, end in enumerate(range(window, values.size)):
        sample = values[end - window : end]
        if method == "historical":
            forecasts[offset] = historical_var_return(sample, level)
        else:
            mean, volatility = sample_mean_and_volatility(sample, zero_mean=zero_mean)
            forecasts[offset] = gaussian_var_return(mean, volatility, level)

    realized = values[window:]
    hits = (realized < -forecasts).astype(int)
    return VarBacktest(
        method=method,
        confidence=level,
        alpha=1.0 - level,
        window=window,
        zero_mean=zero_mean,
        dates=pd.DatetimeIndex(returns.index[window:]),
        realized_returns=realized.copy(),
        var_returns=forecasts,
        hits=hits,
        transitions=transition_counts(hits),
        kupiec=kupiec_unconditional_coverage(hits, 1.0 - level, significance),
        independence=christoffersen_independence(hits, significance),
        conditional=christoffersen_conditional_coverage(hits, 1.0 - level, significance),
    )


def _validate_alpha(alpha: float) -> float:
    try:
        value = float(alpha)
    except (TypeError, ValueError) as exc:
        raise MarketRiskError("tail probability alpha must be in (0, 1)") from exc
    if not math.isfinite(value) or not 0.0 < value < 1.0:
        raise MarketRiskError("tail probability alpha must be in (0, 1)")
    return value


def _xlogy(count: int, probability: float) -> float:
    """``count * ln(probability)``, with ``0 * ln(0)`` defined as 0."""
    if count == 0:
        return 0.0
    if not math.isfinite(probability) or probability <= 0.0:
        return -math.inf
    return count * math.log(probability)


def _binomial_loglik(successes: int, trials: int, probability: float) -> float:
    failures = trials - successes
    return _xlogy(successes, probability) + _xlogy(failures, 1.0 - probability)


def _likelihood_ratio(ll_restricted: float, ll_unrestricted: float) -> float:
    if math.isinf(ll_restricted) and ll_restricted < 0:
        return math.inf
    statistic = -2.0 * (ll_restricted - ll_unrestricted)
    if -1e-9 <= statistic < 0.0:
        return 0.0
    return float(statistic)


def _chi2_survival(statistic: float, degrees: int) -> float:
    if math.isinf(statistic) and statistic > 0:
        return 0.0
    if statistic < 0.0 or not math.isfinite(statistic):
        raise MarketRiskError("likelihood-ratio statistic is not finite")
    p_value = float(chi2.sf(statistic, degrees))
    if not math.isfinite(p_value):
        raise MarketRiskError("failed to compute a chi-square p-value")
    return p_value
