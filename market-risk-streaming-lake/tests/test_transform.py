"""Bronze to silver validation, dedupe, and derived fields."""

from __future__ import annotations

from risk_lake.events import MarketFactorEvent, PnlEvent, PositionEvent
from risk_lake.transform import to_silver


def _pnl(event_id: str, pnl: float, session: str = "2026-01-06") -> dict[str, object]:
    return PnlEvent(
        event_id=event_id,
        event_time=f"{session}T21:00:00Z",
        session_date=session,
        desk="EQ-DELTA-1",
        book="EQ-DELTA-1-BOOK-A",
        instrument_id="SYN-EQ-1",
        pnl=pnl,
    ).to_dict()


def test_silver_dedupes_and_adds_loss() -> None:
    first = _pnl("pnl-2026-01-06-SYN-EQ-1", -25.5)
    duplicate = _pnl("pnl-2026-01-06-SYN-EQ-1", -99)
    later = _pnl("pnl-2026-01-07-SYN-EQ-1", 10, session="2026-01-07")
    silver = to_silver([], [], [first, duplicate, later])

    assert silver.rejected == ()
    assert list(silver.pnl["pnl"]) == [-25.5, 10]
    assert list(silver.pnl["loss"]) == [25.5, -10]
    assert list(silver.pnl["session_date"]) == ["2026-01-06", "2026-01-07"]


def test_silver_rejects_non_finite_and_notional_mismatch() -> None:
    factor = MarketFactorEvent(
        event_id="mf-2026-01-05-SYN-EQ-1",
        event_time="2026-01-05T21:00:00Z",
        session_date="2026-01-05",
        factor_id="SYN-EQ-1",
        asset_class="equity",
        value=100,
        change=0.01,
    ).to_dict()
    factor["change"] = float("nan")

    position = PositionEvent(
        event_id="pos-2026-01-05-SYN-EQ-1",
        event_time="2026-01-05T21:00:00Z",
        session_date="2026-01-05",
        desk="EQ-DELTA-1",
        book="EQ-DELTA-1-BOOK-A",
        instrument_id="SYN-EQ-1",
        quantity=10,
        price=5,
        notional=1,
    ).to_dict()
    good = PositionEvent(
        event_id="pos-2026-01-05-SYN-EQ-2",
        event_time="2026-01-05T21:00:00Z",
        session_date="2026-01-05",
        desk="EQ-DELTA-1",
        book="EQ-DELTA-1-BOOK-A",
        instrument_id="SYN-EQ-2",
        quantity=-4,
        price=10,
        notional=40,
    ).to_dict()

    silver = to_silver([factor], [position, good], [])
    assert silver.market_factors.empty
    assert list(silver.positions["instrument_id"]) == ["SYN-EQ-2"]
    assert silver.positions.iloc[0]["signed_market_value"] == -40
    reasons = " ".join(item.reason for item in silver.rejected)
    assert "finite" in reasons
    assert "notional" in reasons
