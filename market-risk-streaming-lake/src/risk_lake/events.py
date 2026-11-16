"""Event schemas for synthetic market factors, positions, and P&L.

Payloads are plain dictionaries so the same objects can cross the in-memory
bus and a Kafka topic. P&L is signed, with a gain positive. Notional is the
absolute market value of the position.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from risk_lake.errors import RiskLakeError

TOPIC_MARKET_FACTORS = "risk.market-factors"
TOPIC_POSITIONS = "risk.positions"
TOPIC_PNL = "risk.pnl"
TOPICS: tuple[str, ...] = (TOPIC_MARKET_FACTORS, TOPIC_POSITIONS, TOPIC_PNL)

_EVENT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")
_TOKEN = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_SOURCE = re.compile(r"^[a-z0-9_-]{1,32}$")
_ASSET_CLASSES = frozenset({"equity", "rates", "fx", "commodity"})

_FACTOR_FIELDS = frozenset(
    {
        "event_type",
        "event_id",
        "event_time",
        "session_date",
        "factor_id",
        "asset_class",
        "value",
        "change",
        "currency",
        "source",
    }
)
_POSITION_FIELDS = frozenset(
    {
        "event_type",
        "event_id",
        "event_time",
        "session_date",
        "desk",
        "book",
        "instrument_id",
        "quantity",
        "price",
        "notional",
        "currency",
    }
)
_PNL_FIELDS = frozenset(
    {
        "event_type",
        "event_id",
        "event_time",
        "session_date",
        "desk",
        "book",
        "instrument_id",
        "pnl",
        "currency",
    }
)


def canonical_event_time(value: object) -> str:
    """Return an event timestamp as ``YYYY-MM-DDTHH:MM:SSZ``.

    The input must be timezone-aware. Silver storage uses this form so a
    parquet round-trip does not depend on a timestamp type.
    """
    if not isinstance(value, str) or not value.strip():
        raise RiskLakeError("event_time must be an ISO-8601 string")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RiskLakeError(f"event_time is not ISO-8601: {text}") from exc
    if parsed.tzinfo is None:
        raise RiskLakeError("event_time must include a timezone")
    utc = parsed.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_session_date(value: object) -> str:
    """Return a business date as ``YYYY-MM-DD``."""
    if not isinstance(value, str):
        raise RiskLakeError("session_date must be a YYYY-MM-DD string")
    text = value.strip()
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise RiskLakeError(f"session_date is not YYYY-MM-DD: {text}") from exc
    return parsed.strftime("%Y-%m-%d")


def _require_fields(raw: Mapping[str, object], expected: frozenset[str], event_type: str) -> None:
    keys = set(raw)
    missing = sorted(expected - keys)
    extra = sorted(keys - expected)
    if missing or extra:
        raise RiskLakeError(
            f"{event_type} payload has missing fields {missing or 'none'} "
            f"and unexpected fields {extra or 'none'}"
        )


def _text(raw: Mapping[str, object], name: str, pattern: re.Pattern[str]) -> str:
    value = raw[name]
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise RiskLakeError(f"{name} has an unexpected form")
    return value


def _number(raw: Mapping[str, object], name: str) -> float:
    value = raw[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RiskLakeError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise RiskLakeError(f"{name} must be finite")
    return number


@dataclass(frozen=True)
class MarketFactorEvent:
    """One synthetic risk-factor level on one session."""

    event_id: str
    event_time: str
    session_date: str
    factor_id: str
    asset_class: str
    value: float
    change: float
    currency: str = "USD"
    source: str = "synthetic"

    @property
    def topic(self) -> str:
        return TOPIC_MARKET_FACTORS

    @property
    def key(self) -> str:
        return self.event_id

    def to_dict(self) -> dict[str, object]:
        return {
            "event_type": "market_factor",
            "event_id": self.event_id,
            "event_time": self.event_time,
            "session_date": self.session_date,
            "factor_id": self.factor_id,
            "asset_class": self.asset_class,
            "value": self.value,
            "change": self.change,
            "currency": self.currency,
            "source": self.source,
        }


@dataclass(frozen=True)
class PositionEvent:
    """One synthetic holding. ``notional`` is absolute market value."""

    event_id: str
    event_time: str
    session_date: str
    desk: str
    book: str
    instrument_id: str
    quantity: float
    price: float
    notional: float
    currency: str = "USD"

    @property
    def topic(self) -> str:
        return TOPIC_POSITIONS

    @property
    def key(self) -> str:
        return self.event_id

    def to_dict(self) -> dict[str, object]:
        return {
            "event_type": "position",
            "event_id": self.event_id,
            "event_time": self.event_time,
            "session_date": self.session_date,
            "desk": self.desk,
            "book": self.book,
            "instrument_id": self.instrument_id,
            "quantity": self.quantity,
            "price": self.price,
            "notional": self.notional,
            "currency": self.currency,
        }


@dataclass(frozen=True)
class PnlEvent:
    """One synthetic P&L. A positive number is a gain."""

    event_id: str
    event_time: str
    session_date: str
    desk: str
    book: str
    instrument_id: str
    pnl: float
    currency: str = "USD"

    @property
    def topic(self) -> str:
        return TOPIC_PNL

    @property
    def key(self) -> str:
        return self.event_id

    def to_dict(self) -> dict[str, object]:
        return {
            "event_type": "pnl",
            "event_id": self.event_id,
            "event_time": self.event_time,
            "session_date": self.session_date,
            "desk": self.desk,
            "book": self.book,
            "instrument_id": self.instrument_id,
            "pnl": self.pnl,
            "currency": self.currency,
        }


RiskEvent = MarketFactorEvent | PositionEvent | PnlEvent


def parse_market_factor(raw: Mapping[str, object]) -> MarketFactorEvent:
    """Validate a market-factor payload and return the event."""
    _require_fields(raw, _FACTOR_FIELDS, "market_factor")
    if raw["event_type"] != "market_factor":
        raise RiskLakeError("event_type must be market_factor")
    asset_class = raw["asset_class"]
    if not isinstance(asset_class, str) or asset_class not in _ASSET_CLASSES:
        raise RiskLakeError("asset_class must be equity, rates, fx, or commodity")
    value = _number(raw, "value")
    if value <= 0.0:
        raise RiskLakeError("factor value must be positive")
    return MarketFactorEvent(
        event_id=_text(raw, "event_id", _EVENT_ID),
        event_time=canonical_event_time(raw["event_time"]),
        session_date=canonical_session_date(raw["session_date"]),
        factor_id=_text(raw, "factor_id", _TOKEN),
        asset_class=asset_class,
        value=value,
        change=_number(raw, "change"),
        currency=_text(raw, "currency", _CURRENCY),
        source=_text(raw, "source", _SOURCE),
    )


def parse_position(raw: Mapping[str, object]) -> PositionEvent:
    """Validate a position payload and return the event."""
    _require_fields(raw, _POSITION_FIELDS, "position")
    if raw["event_type"] != "position":
        raise RiskLakeError("event_type must be position")
    price = _number(raw, "price")
    notional = _number(raw, "notional")
    if price <= 0.0:
        raise RiskLakeError("price must be positive")
    if notional < 0.0:
        raise RiskLakeError("notional must be zero or positive")
    return PositionEvent(
        event_id=_text(raw, "event_id", _EVENT_ID),
        event_time=canonical_event_time(raw["event_time"]),
        session_date=canonical_session_date(raw["session_date"]),
        desk=_text(raw, "desk", _TOKEN),
        book=_text(raw, "book", _TOKEN),
        instrument_id=_text(raw, "instrument_id", _TOKEN),
        quantity=_number(raw, "quantity"),
        price=price,
        notional=notional,
        currency=_text(raw, "currency", _CURRENCY),
    )


def parse_pnl(raw: Mapping[str, object]) -> PnlEvent:
    """Validate a P&L payload and return the event."""
    _require_fields(raw, _PNL_FIELDS, "pnl")
    if raw["event_type"] != "pnl":
        raise RiskLakeError("event_type must be pnl")
    return PnlEvent(
        event_id=_text(raw, "event_id", _EVENT_ID),
        event_time=canonical_event_time(raw["event_time"]),
        session_date=canonical_session_date(raw["session_date"]),
        desk=_text(raw, "desk", _TOKEN),
        book=_text(raw, "book", _TOKEN),
        instrument_id=_text(raw, "instrument_id", _TOKEN),
        pnl=_number(raw, "pnl"),
        currency=_text(raw, "currency", _CURRENCY),
    )


def parse_event(raw: Mapping[str, object]) -> RiskEvent:
    """Parse one payload, using ``event_type`` to choose the schema."""
    event_type = raw.get("event_type")
    if event_type == "market_factor":
        return parse_market_factor(raw)
    if event_type == "position":
        return parse_position(raw)
    if event_type == "pnl":
        return parse_pnl(raw)
    raise RiskLakeError("event_type must be market_factor, position, or pnl")
