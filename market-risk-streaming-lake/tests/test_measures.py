"""Hand-checked historical VaR and Expected Shortfall on P&L."""

from __future__ import annotations

import numpy as np
import pytest

from risk_lake.measures import historical_es_loss, historical_var_loss


def test_var_matches_type_7_quantile() -> None:
    # n = 4, p = 0.05. Index (n - 1) * p = 0.15 between the worst and the next.
    sample = np.array([-100.0, -1.0, -1.0, -1.0])
    quantile = -100.0 + 0.15 * (-1.0 - (-100.0))
    assert historical_var_loss(sample, 0.95) == pytest.approx(-quantile)
    assert historical_var_loss(sample, 0.95) == pytest.approx(85.15)


def test_es_fractional_and_integer_tails() -> None:
    fractional = np.array([-100.0, -1.0, -1.0, -1.0])
    # u = 4 * 0.05 = 0.2, so ES is the worst point, written as a loss.
    assert historical_es_loss(fractional, 0.95) == 100.0

    # u = 5 * 0.2 = 1 exactly, so ES is the single worst P&L.
    integer = np.array([-10.0, -4.0, 0.0, 1.0, 2.0])
    assert historical_es_loss(integer, 0.80) == 10.0
    # p = 0.2, index (5 - 1) * 0.2 = 0.8.
    assert historical_var_loss(integer, 0.80) == pytest.approx(-(-10.0 + 0.8 * (-4.0 - (-10.0))))
