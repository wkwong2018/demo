"""Historical VaR and Expected Shortfall on a book's own P&L.

P&L is signed, gain positive. Both results are loss amounts: a positive
number is a loss threshold. This is the same pair of estimators described
for returns in the sibling ``market-risk-var-es`` project (Hyndman-Fan type
7, and Acerbi's tail average). It is reimplemented here so this demo does
not import that package.

The sample is the book's recent daily P&L, equally weighted. There is no
volatility scaling, no decay, and no full revaluation.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike

from risk_lake.errors import RiskLakeError


def validate_confidence(confidence: float) -> float:
    """Return a confidence level in (0, 1)."""
    try:
        value = float(confidence)
    except (TypeError, ValueError) as exc:
        raise RiskLakeError("confidence must be a probability in (0, 1)") from exc
    if isinstance(confidence, bool) or not math.isfinite(value) or not 0.0 < value < 1.0:
        raise RiskLakeError("confidence must be a probability in (0, 1)")
    return value


def as_pnl(values: ArrayLike, *, min_size: int = 2) -> np.ndarray:
    """Copy a finite one-dimensional P&L sample."""
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise RiskLakeError("pnl must be one-dimensional")
    if array.size < min_size:
        raise RiskLakeError(f"pnl must contain at least {min_size} observations")
    if not np.isfinite(array).all():
        raise RiskLakeError("pnl must be finite")
    return array


def historical_var_loss(pnl: ArrayLike, confidence: float) -> float:
    """Historical-simulation VaR as a positive loss amount.

    ``VaR(c) = -quantile(pnl, 1 - c)`` with the Hyndman-Fan type 7 quantile
    (NumPy's linear method). A negative result means the threshold outcome
    is a gain.
    """
    sample = as_pnl(pnl)
    level = validate_confidence(confidence)
    quantile = float(np.quantile(sample, 1.0 - level, method="linear"))
    return -quantile


def historical_es_loss(pnl: ArrayLike, confidence: float) -> float:
    """Historical Expected Shortfall as a positive loss amount.

    With ordered P&L ``R(1) <= ... <= R(n)``, ``alpha = 1 - c``,
    ``u = n * alpha``, and ``k = floor(u)``:

        ES(c) = -1/u * (sum of R(1)..R(k) + (u - k) * R(k+1))

    When ``u`` is an integer this is the average of the worst ``u`` P&L
    values, written as a loss. A value of ``u`` that misses an integer only
    by binary rounding is treated as that integer.
    """
    sample = as_pnl(pnl)
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
            raise RiskLakeError("tail probability is too small for this sample")
        return -float(np.mean(ordered[:k]))

    tail = float(ordered[:k].sum()) + fraction * float(ordered[k])
    return -tail / mass


def _tail_mass(n: int, confidence: float) -> float:
    """Return ``n * (1 - confidence)``, snapping ulp-sized misses off integers."""
    mass = n * (1.0 - confidence)
    nearest = round(mass)
    tolerance = 1e-8 * max(n, 1)
    if abs(mass - nearest) <= tolerance:
        mass = float(nearest)
    if mass <= 0.0:
        raise RiskLakeError(
            "tail probability is too small for this sample; "
            "lower the confidence or lengthen the window"
        )
    if mass > n:
        return float(n)
    return mass
