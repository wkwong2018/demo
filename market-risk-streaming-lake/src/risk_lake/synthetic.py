"""Seeded synthetic factor, position, and P&L events.

The path is a zero-drift geometric random walk. The last session is then
overwritten with a fixed scenario so the equity book lands over its notional
and daily-loss limits for the default seed. Rates and FX are flat on that
session. Weekdays are used; there is no holiday calendar.

P&L on session t is ``quantity_t * (price_t - price_t-1)``. The demo applies
the last session's new quantity to that session's price change. A real P&L
explain would split the quantity change from the market move. Prices are
kept positive. Factor levels are rounded to 6 decimal places, changes to 8,
and currency amounts to cents.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from risk_lake.errors import RiskLakeError
from risk_lake.events import MarketFactorEvent, PnlEvent, PositionEvent, RiskEvent

_START = "2026-01-05"
_CLOSE_TIME = "T21:00:00Z"


@dataclass(frozen=True)
class InstrumentSpec:
    """One linear instrument held by one book."""

    instrument_id: str
    asset_class: str
    start_price: float
    daily_vol: float
    quantity: float
    desk: str
    book: str


INSTRUMENTS: tuple[InstrumentSpec, ...] = (
    InstrumentSpec("SYN-EQ-1", "equity", 100.0, 0.012, 20_000.0, "EQ-DELTA-1", "EQ-DELTA-1-BOOK-A"),
    InstrumentSpec("SYN-EQ-2", "equity", 80.0, 0.015, 10_000.0, "EQ-DELTA-1", "EQ-DELTA-1-BOOK-A"),
    InstrumentSpec("SYN-FI-1", "rates", 102.0, 0.003, 50_000.0, "FI-RATES-1", "FI-RATES-1-BOOK-A"),
    InstrumentSpec("SYN-FI-2", "rates", 99.0, 0.0035, 40_000.0, "FI-RATES-1", "FI-RATES-1-BOOK-A"),
    InstrumentSpec("SYN-FX-1", "fx", 1.25, 0.005, 1_500_000.0, "FX-SPOT-1", "FX-SPOT-1-BOOK-A"),
)

# Last-session overlay. Equity sells off and the first equity line is sized up.
# The other books do not move, so the snapshot breach is the equity book.
SCRIPTED_LAST_SHOCK: dict[str, float] = {
    "SYN-EQ-1": -0.08,
    "SYN-EQ-2": -0.01,
    "SYN-FI-1": 0.0,
    "SYN-FI-2": 0.0,
    "SYN-FX-1": 0.0,
}
SCRIPTED_LAST_QUANTITY: dict[str, float] = {
    "SYN-EQ-1": 45_000.0,
}


def session_dates(sessions: int) -> pd.DatetimeIndex:
    """Weekday sessions starting 5 January 2026."""
    if sessions < 2:
        raise RiskLakeError("sessions must be at least 2")
    return pd.bdate_range(_START, periods=sessions)


def generate_events(*, sessions: int = 60, seed: int = 7) -> list[RiskEvent]:
    """Build market-factor, position, and P&L events in session order."""
    dates = session_dates(sessions)
    rng = np.random.default_rng(seed)
    events: list[RiskEvent] = []
    for spec in INSTRUMENTS:
        events.extend(_instrument_events(spec, dates, rng))
    events.sort(key=lambda event: (event.session_date, event.topic, event.event_id))
    return events


def _instrument_events(
    spec: InstrumentSpec,
    dates: pd.DatetimeIndex,
    rng: np.random.Generator,
) -> list[RiskEvent]:
    shocks = rng.normal(0.0, spec.daily_vol, size=len(dates))
    shocks[-1] = SCRIPTED_LAST_SHOCK[spec.instrument_id]
    quantities = np.full(len(dates), spec.quantity, dtype=float)
    if spec.instrument_id in SCRIPTED_LAST_QUANTITY:
        quantities[-1] = SCRIPTED_LAST_QUANTITY[spec.instrument_id]

    events: list[RiskEvent] = []
    previous = spec.start_price
    for index, timestamp in enumerate(dates):
        shock = float(shocks[index])
        if shock <= -1.0:
            raise RiskLakeError(f"{spec.instrument_id} shock would make the price non-positive")
        price = previous * (1.0 + shock)
        if not math.isfinite(price) or price <= 0.0:
            raise RiskLakeError(f"{spec.instrument_id} price left the positive reals")
        quantity = float(quantities[index])
        session = timestamp.strftime("%Y-%m-%d")
        event_time = session + _CLOSE_TIME
        level = round(price, 6)
        change = round(shock, 8)
        notional = round(abs(quantity * level), 2)
        pnl = round(quantity * (level - round(previous, 6)), 2)
        previous = level

        events.append(
            MarketFactorEvent(
                event_id=f"mf-{session}-{spec.instrument_id}",
                event_time=event_time,
                session_date=session,
                factor_id=spec.instrument_id,
                asset_class=spec.asset_class,
                value=level,
                change=change,
                currency="USD",
                source="synthetic",
            )
        )
        events.append(
            PositionEvent(
                event_id=f"pos-{session}-{spec.instrument_id}",
                event_time=event_time,
                session_date=session,
                desk=spec.desk,
                book=spec.book,
                instrument_id=spec.instrument_id,
                quantity=quantity,
                price=level,
                notional=notional,
                currency="USD",
            )
        )
        events.append(
            PnlEvent(
                event_id=f"pnl-{session}-{spec.instrument_id}",
                event_time=event_time,
                session_date=session,
                desk=spec.desk,
                book=spec.book,
                instrument_id=spec.instrument_id,
                pnl=pnl,
                currency="USD",
            )
        )
    return events
