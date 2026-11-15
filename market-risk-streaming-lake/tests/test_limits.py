"""Known-breach fixture and the checked-in limit file."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from risk_lake.limits import BookLimit, LimitConfig, build_snapshot, load_limits, sibling_price_frame

_DATES = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]


def _config() -> LimitConfig:
    return LimitConfig(
        currency="USD",
        confidence=0.95,
        var_window=4,
        books=(
            BookLimit(
                desk="EQ-DELTA-1",
                book="EQ-DELTA-1-BOOK-A",
                index_name="SYN-EQ-BOOK",
                notional=1_000_000,
                daily_loss=50,
                var=10,
            ),
            BookLimit(
                desk="FI-RATES-1",
                book="FI-RATES-1-BOOK-A",
                index_name="SYN-FI-BOOK",
                notional=1_000,
                daily_loss=50,
                var=50,
            ),
        ),
    )


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "session_date": _DATES + _DATES,
            "desk": ["EQ-DELTA-1"] * 4 + ["FI-RATES-1"] * 4,
            "book": ["EQ-DELTA-1-BOOK-A"] * 4 + ["FI-RATES-1-BOOK-A"] * 4,
            "notional": [1_000.0, 1_000.0, 1_000.0, 2_000_000.0, 100.0, 100.0, 100.0, 100.0],
            "pnl": [-1.0, -1.0, -1.0, -100.0, 5.0, 5.0, 5.0, 5.0],
        }
    )


def test_known_breach_and_quiet_book() -> None:
    snapshot = build_snapshot(_panel(), _config())
    assert snapshot.as_of == "2026-01-08"
    equity = snapshot.rows.loc[snapshot.rows["book"] == "EQ-DELTA-1-BOOK-A"].iloc[0]
    quiet = snapshot.rows.loc[snapshot.rows["book"] == "FI-RATES-1-BOOK-A"].iloc[0]

    assert equity["notional_breach"]
    assert equity["daily_loss_breach"]
    assert equity["var_breach"]
    assert equity["status"] == "breach"
    assert equity["gross_notional"] == 2_000_000
    assert equity["notional_utilization"] == 2
    assert equity["daily_loss"] == 100
    assert equity["daily_loss_utilization"] == 2
    assert equity["var_loss"] == pytest.approx(85.15)
    assert equity["es_loss"] == pytest.approx(100)

    assert quiet["status"] == "inside"
    assert not quiet["notional_breach"]
    assert not quiet["daily_loss_breach"]
    assert not quiet["var_breach"]
    assert quiet["daily_loss"] == 0
    assert quiet["var_loss"] == -5

    metrics = {(item.book, item.metric) for item in snapshot.breaches}
    assert metrics == {
        ("EQ-DELTA-1-BOOK-A", "gross_notional"),
        ("EQ-DELTA-1-BOOK-A", "daily_loss"),
        ("EQ-DELTA-1-BOOK-A", "historical_var"),
    }
    assert snapshot.breaches[0].utilization == max(item.utilization for item in snapshot.breaches)


def test_price_index_compounds_prior_notional() -> None:
    frame = sibling_price_frame(_panel(), _config())
    assert list(frame["date"]) == _DATES
    # Quiet book: prior notional 100 and P&L +5, so each return is 5%.
    assert list(frame["SYN-FI-BOOK"]) == [100.0, 105.0, 110.25, 115.7625]
    assert (frame[["SYN-EQ-BOOK", "SYN-FI-BOOK"]] > 0).all().all()


def test_checked_in_limits_cover_the_three_demo_books() -> None:
    path = Path(__file__).resolve().parents[1] / "config" / "limits.yml"
    config = load_limits(path)
    assert config.currency == "USD"
    assert config.confidence == 0.95
    assert config.var_window == 40
    assert [item.book for item in config.books] == [
        "EQ-DELTA-1-BOOK-A",
        "FI-RATES-1-BOOK-A",
        "FX-SPOT-1-BOOK-A",
    ]
    assert [item.index_name for item in config.books] == ["SYN-EQ", "SYN-FI", "SYN-FX"]
