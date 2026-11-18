"""Shared fixtures. The sample explain is computed once per test session."""

from __future__ import annotations

import pytest

from pnl_attribution import explain_book, load_sample_book
from pnl_attribution.explain import ExplainResult


@pytest.fixture(scope="session")
def sample_result() -> ExplainResult:
    return explain_book(load_sample_book())
