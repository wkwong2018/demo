"""Shared checks for confidences, samples, and hit series."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from numpy.typing import ArrayLike

from market_risk.errors import MarketRiskError


def validate_confidence(confidence: float) -> float:
    """Return a confidence level in (0, 1), such as 0.99."""
    try:
        value = float(confidence)
    except (TypeError, ValueError) as exc:
        raise MarketRiskError(
            "confidence must be a probability in (0, 1), for example 0.99"
        ) from exc
    if not math.isfinite(value) or not 0.0 < value < 1.0:
        raise MarketRiskError(
            "confidence must be a probability in (0, 1), for example 0.99"
        )
    return value


def validate_significance(significance: float) -> float:
    """Return a hypothesis-test size in (0, 1)."""
    try:
        value = float(significance)
    except (TypeError, ValueError) as exc:
        raise MarketRiskError("significance must be a probability in (0, 1)") from exc
    if not math.isfinite(value) or not 0.0 < value < 1.0:
        raise MarketRiskError("significance must be a probability in (0, 1)")
    return value


def validate_portfolio_value(portfolio_value: float) -> float:
    """Return a positive finite portfolio value."""
    try:
        value = float(portfolio_value)
    except (TypeError, ValueError) as exc:
        raise MarketRiskError("portfolio value must be a positive finite number") from exc
    if not math.isfinite(value) or value <= 0.0:
        raise MarketRiskError("portfolio value must be a positive finite number")
    return value


def validate_confidences(confidences: Sequence[float]) -> tuple[float, ...]:
    """Validate confidence levels and reject duplicates."""
    if len(confidences) == 0:
        raise MarketRiskError("provide at least one confidence level")
    validated = tuple(validate_confidence(confidence) for confidence in confidences)
    if len(set(validated)) != len(validated):
        raise MarketRiskError("confidence levels must be unique")
    return validated


def as_1d_float(values: ArrayLike, *, name: str, min_size: int = 2) -> np.ndarray:
    """Copy a finite one-dimensional sample."""
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise MarketRiskError(f"{name} must be one-dimensional")
    if array.size < min_size:
        raise MarketRiskError(f"{name} must contain at least {min_size} observations")
    if not np.isfinite(array).all():
        raise MarketRiskError(f"{name} must be finite")
    return array


def as_hits(hits: ArrayLike) -> np.ndarray:
    """Return a 0/1 hit series. One means the loss exceeded VaR."""
    array = np.asarray(hits)
    if array.ndim != 1 or array.size < 1:
        raise MarketRiskError("hits must be a non-empty one-dimensional sequence")
    if array.dtype == bool:
        return array.astype(int)
    values = array.astype(float)
    if not np.isfinite(values).all() or not np.isin(values, (0.0, 1.0)).all():
        raise MarketRiskError("hits must contain only 0 and 1")
    return values.astype(int)
