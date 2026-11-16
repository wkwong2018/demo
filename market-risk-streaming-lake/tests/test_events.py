"""Event schema checks."""

from __future__ import annotations

import pytest

from risk_lake.errors import RiskLakeError
from risk_lake.events import (
    MarketFactorEvent,
    PnlEvent,
    PositionEvent,
    parse_event,
    parse_market_factor,
    parse_pnl,
    parse_position,
)
from risk_lake.synthetic import SCRIPTED_LAST_QUANTITY, SCRIPTED_LAST_SHOCK, generate_events


def _factor() -> MarketFactorEvent:
    return MarketFactorEvent(
        event_id="mf-2026-01-05-SYN-EQ-1",
        event_time="2026-01-05T21:00:00Z",
        session_date="2026-01-05",
        factor_id="SYN-EQ-1",
        asset_class="equity",
        value=100.0,
        change=-0.01,
        currency="USD",
        source="synthetic",
    )


def test_market_factor_round_trip() -> None:
    event = _factor()
    assert parse_market_factor(event.to_dict()) == event
    assert event.topic == "risk.market-factors"
    assert event.key == event.event_id


def test_position_and_pnl_round_trip() -> None:
    position = PositionEvent(
        event_id="pos-2026-01-05-SYN-EQ-1",
        event_time="2026-01-05T21:00:00+00:00",
        session_date="2026-01-05",
        desk="EQ-DELTA-1",
        book="EQ-DELTA-1-BOOK-A",
        instrument_id="SYN-EQ-1",
        quantity=20_000,
        price=100.0,
        notional=2_000_000,
    )
    parsed = parse_position(position.to_dict())
    assert parsed.event_time == "2026-01-05T21:00:00Z"
    assert parsed.quantity == 20_000

    pnl = PnlEvent(
        event_id="pnl-2026-01-05-SYN-EQ-1",
        event_time="2026-01-05T21:00:00Z",
        session_date="2026-01-05",
        desk="EQ-DELTA-1",
        book="EQ-DELTA-1-BOOK-A",
        instrument_id="SYN-EQ-1",
        pnl=-1500.5,
    )
    assert parse_pnl(pnl.to_dict()) == pnl


def test_schema_rejects_bad_payloads() -> None:
    payload = _factor().to_dict()
    payload["value"] = float("inf")
    with pytest.raises(RiskLakeError, match="finite"):
        parse_market_factor(payload)

    payload = _factor().to_dict()
    payload["value"] = 0
    with pytest.raises(RiskLakeError, match="positive"):
        parse_market_factor(payload)

    payload = _factor().to_dict()
    del payload["factor_id"]
    with pytest.raises(RiskLakeError, match="missing"):
        parse_market_factor(payload)

    payload = _factor().to_dict()
    payload["surprise"] = 1
    with pytest.raises(RiskLakeError, match="unexpected"):
        parse_market_factor(payload)

    payload = _factor().to_dict()
    payload["session_date"] = "05-01-2026"
    with pytest.raises(RiskLakeError, match="session_date"):
        parse_event(payload)

    payload = _factor().to_dict()
    payload["event_time"] = "2026-01-05T21:00:00"
    with pytest.raises(RiskLakeError, match="timezone"):
        parse_event(payload)


def test_default_scenario_scripts_the_last_equity_session() -> None:
    events = generate_events(sessions=5, seed=7)
    last_date = max(event.session_date for event in events)
    factors = [
        event
        for event in events
        if isinstance(event, MarketFactorEvent) and event.session_date == last_date
    ]
    by_id = {event.factor_id: event.change for event in factors}
    assert by_id == SCRIPTED_LAST_SHOCK

    positions = [
        event
        for event in events
        if isinstance(event, PositionEvent) and event.session_date == last_date
    ]
    sized = {event.instrument_id: event.quantity for event in positions}
    assert sized["SYN-EQ-1"] == SCRIPTED_LAST_QUANTITY["SYN-EQ-1"]
    assert sized["SYN-FI-1"] == 50_000
