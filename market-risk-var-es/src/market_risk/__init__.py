"""One-day VaR, Expected Shortfall, and coverage backtests.

Personal methodology demo. Not a risk system and not investment advice.
"""

from market_risk.analysis import run_analysis
from market_risk.backtest import (
    christoffersen_conditional_coverage,
    christoffersen_independence,
    kupiec_unconditional_coverage,
    rolling_var_backtest,
)
from market_risk.errors import MarketRiskError
from market_risk.portfolio import (
    SAMPLE_WEIGHTS,
    align_weights,
    bundled_sample_prices_path,
    load_prices,
    portfolio_returns,
    simple_returns,
)
from market_risk.risk import (
    gaussian_es_return,
    gaussian_var_return,
    historical_es_return,
    historical_var_return,
    parametric_es_return,
    parametric_var_return,
)
from market_risk.version import __version__

__all__ = [
    "MarketRiskError",
    "SAMPLE_WEIGHTS",
    "align_weights",
    "bundled_sample_prices_path",
    "christoffersen_conditional_coverage",
    "christoffersen_independence",
    "gaussian_es_return",
    "gaussian_var_return",
    "historical_es_return",
    "historical_var_return",
    "kupiec_unconditional_coverage",
    "load_prices",
    "parametric_es_return",
    "parametric_var_return",
    "portfolio_returns",
    "rolling_var_backtest",
    "run_analysis",
    "simple_returns",
]
