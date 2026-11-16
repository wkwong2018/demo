"""Bronze payloads to silver tables.

Silver keeps the first valid copy of each ``event_id``, normalizes the
timestamp to UTC seconds, and adds:

- positions: ``signed_market_value = quantity * price``, and a check that
  ``notional`` matches the absolute market value within two cents
- P&L: ``loss = -pnl`` so later steps can talk about losses as positive numbers

A row that fails validation is returned in ``rejected`` and is not written.
The happy-path demo raises if that collection is non-empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Mapping, Sequence

import pandas as pd

from risk_lake.errors import RiskLakeError
from risk_lake.events import (
    MarketFactorEvent,
    PnlEvent,
    PositionEvent,
    parse_market_factor,
    parse_pnl,
    parse_position,
)

_NOTIONAL_TOLERANCE = 0.02


@dataclass(frozen=True)
class Reject:
    """One bronze row that silver refused."""

    event_id: str
    reason: str


@dataclass(frozen=True)
class SilverTables:
    """Validated frames and the rows that were refused."""

    market_factors: pd.DataFrame
    positions: pd.DataFrame
    pnl: pd.DataFrame
    rejected: tuple[Reject, ...]


def to_silver(
    market_factors: Sequence[Mapping[str, object]],
    positions: Sequence[Mapping[str, object]],
    pnl: Sequence[Mapping[str, object]],
) -> SilverTables:
    """Validate, dedupe, and type the three bronze datasets."""
    factor_rows, factor_rejected = _collect(market_factors, parse_market_factor, _factor_row)
    position_rows, position_rejected = _collect(positions, parse_position, _position_row)
    pnl_rows, pnl_rejected = _collect(pnl, parse_pnl, _pnl_row)
    return SilverTables(
        market_factors=_frame(factor_rows, _FACTOR_COLUMNS),
        positions=_frame(position_rows, _POSITION_COLUMNS),
        pnl=_frame(pnl_rows, _PNL_COLUMNS),
        rejected=factor_rejected + position_rejected + pnl_rejected,
    )


def _collect(records, parser, derive: Callable[..., dict[str, object]]):
    kept: list[dict[str, object]] = []
    rejected: list[Reject] = []
    seen: set[str] = set()
    for raw in records:
        if not isinstance(raw, Mapping):
            rejected.append(Reject(event_id="", reason="payload must be an object"))
            continue
        try:
            event = parser(_plain_record(raw))
            row = derive(event)
        except RiskLakeError as exc:
            rejected.append(Reject(event_id=_peek_id(raw), reason=str(exc)))
            continue
        event_id = str(row["event_id"])
        if event_id in seen:
            continue
        seen.add(event_id)
        kept.append(row)
    return kept, tuple(rejected)


def _factor_row(event: MarketFactorEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "event_time": event.event_time,
        "session_date": event.session_date,
        "factor_id": event.factor_id,
        "asset_class": event.asset_class,
        "value": event.value,
        "change": event.change,
        "currency": event.currency,
        "source": event.source,
    }


def _position_row(event: PositionEvent) -> dict[str, object]:
    signed = event.quantity * event.price
    if abs(abs(signed) - event.notional) > _NOTIONAL_TOLERANCE:
        raise RiskLakeError(
            f"notional {event.notional} does not match abs(quantity * price) {abs(signed):.2f}"
        )
    return {
        "event_id": event.event_id,
        "event_time": event.event_time,
        "session_date": event.session_date,
        "desk": event.desk,
        "book": event.book,
        "instrument_id": event.instrument_id,
        "quantity": event.quantity,
        "price": event.price,
        "notional": event.notional,
        "signed_market_value": round(signed, 2),
        "currency": event.currency,
    }


def _pnl_row(event: PnlEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "event_time": event.event_time,
        "session_date": event.session_date,
        "desk": event.desk,
        "book": event.book,
        "instrument_id": event.instrument_id,
        "pnl": event.pnl,
        "loss": -event.pnl,
        "currency": event.currency,
    }


def _frame(rows: list[dict[str, object]], columns: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=list(columns))
    if frame.empty:
        return frame
    return frame.sort_values(["session_date", "event_id"], kind="mergesort").reset_index(drop=True)


def _plain_record(raw: Mapping[str, object]) -> dict[str, object]:
    """Turn parquet / NumPy scalars back into JSON-like Python values."""
    plain: dict[str, object] = {}
    for key, value in raw.items():
        plain[str(key)] = _plain_value(value)
    return plain


def _plain_value(value: object) -> object:
    if isinstance(value, str) or value is None or isinstance(value, bool):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    return value


def _peek_id(raw: object) -> str:
    if isinstance(raw, Mapping):
        event_id = raw.get("event_id", "")
        if isinstance(event_id, str):
            return event_id
    return ""


_FACTOR_COLUMNS = (
    "event_id",
    "event_time",
    "session_date",
    "factor_id",
    "asset_class",
    "value",
    "change",
    "currency",
    "source",
)
_POSITION_COLUMNS = (
    "event_id",
    "event_time",
    "session_date",
    "desk",
    "book",
    "instrument_id",
    "quantity",
    "price",
    "notional",
    "signed_market_value",
    "currency",
)
_PNL_COLUMNS = (
    "event_id",
    "event_time",
    "session_date",
    "desk",
    "book",
    "instrument_id",
    "pnl",
    "loss",
    "currency",
)
