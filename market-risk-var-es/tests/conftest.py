"""Shared fixtures. The sample analysis is computed once per test session."""

from __future__ import annotations

import pytest

from market_risk.analysis import AnalysisResult, run_analysis
from market_risk.portfolio import SAMPLE_WEIGHTS, bundled_sample_prices_path, load_prices


@pytest.fixture(scope="session")
def sample_prices():
    return load_prices(bundled_sample_prices_path())


@pytest.fixture(scope="session")
def sample_analysis(sample_prices) -> AnalysisResult:
    return run_analysis(sample_prices, SAMPLE_WEIGHTS)
