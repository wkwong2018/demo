"""Errors raised by the risk engine."""

from __future__ import annotations


class MarketRiskError(Exception):
    """Inputs cannot support a risk estimate or a backtest."""
