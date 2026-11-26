"""Snapshot book: positions, stated factor returns, and betas.

Prices and quantities are decimals, not binary floats. A float is rejected
so a value such as 0.1 cannot arrive already rounded in base 2.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence

from pnl_attribution.errors import PnlAttributionError

# A label for the shipped snapshot. It is not looked up on a calendar.
SAMPLE_SESSION = "2026-06-12"

_POSITION_REQUIRED = ("instrument", "qty_start", "qty_end", "price_start", "price_end")
_POSITION_OPTIONAL = ("reported_pnl",)
_FACTOR_REQUIRED = ("factor", "simple_return")
_LOADING_REQUIRED = ("instrument", "factor", "beta")


@dataclass(frozen=True)
class Position:
    """One linear instrument at the start and the end of the session.

    ``reported_pnl`` is an optional external session P&L, for example a ledger
    figure. When it is omitted, the explain uses the linear model and the
    residual is zero.
    """

    instrument: str
    qty_start: Decimal | int
    qty_end: Decimal | int
    price_start: Decimal | int
    price_end: Decimal | int
    reported_pnl: Decimal | int | None = None


@dataclass(frozen=True)
class FactorReturn:
    """A named factor's simple return over the session. This is an input."""

    factor: str
    simple_return: Decimal | int


@dataclass(frozen=True)
class Loading:
    """Stated beta of one instrument on one factor. Not a fitted coefficient."""

    instrument: str
    factor: str
    beta: Decimal | int


@dataclass(frozen=True)
class Book:
    """A validated snapshot. Quantities and prices are finite decimals."""

    positions: tuple[Position, ...]
    factors: tuple[FactorReturn, ...]
    loadings: tuple[Loading, ...]
    session: str = SAMPLE_SESSION
    currency: str = "USD"


def bundled_positions_path() -> Path:
    """Path to the synthetic position file shipped with this project."""
    return _bundled("positions.csv")


def bundled_factors_path() -> Path:
    """Path to the synthetic factor-return file shipped with this project."""
    return _bundled("factors.csv")


def bundled_loadings_path() -> Path:
    """Path to the synthetic beta file shipped with this project."""
    return _bundled("loadings.csv")


def load_sample_book(session: str = SAMPLE_SESSION) -> Book:
    """Load the shipped snapshot. The session argument only changes the label."""
    return load_book(
        bundled_positions_path(),
        bundled_factors_path(),
        bundled_loadings_path(),
        session=session,
    )


def load_book(
    positions: str | Path,
    factors: str | Path,
    loadings: str | Path,
    *,
    session: str = SAMPLE_SESSION,
) -> Book:
    """Load a snapshot from three CSV files.

    Position columns: ``instrument``, ``qty_start``, ``qty_end``,
    ``price_start``, ``price_end``, and optional ``reported_pnl``.
    Factor columns: ``factor``, ``simple_return``.
    Loading columns: ``instrument``, ``factor``, ``beta``.
    Headers are matched without case or surrounding space. Names are matched
    exactly after surrounding space is removed.
    """
    position_rows = _read_table(
        Path(positions),
        required=_POSITION_REQUIRED,
        optional=_POSITION_OPTIONAL,
    )
    factor_rows = _read_table(Path(factors), required=_FACTOR_REQUIRED)
    loading_rows = _read_table(Path(loadings), required=_LOADING_REQUIRED)
    return make_book(
        [
            Position(
                instrument=row["instrument"],
                qty_start=_decimal(row["qty_start"], label=f"{row['instrument']} qty_start"),
                qty_end=_decimal(row["qty_end"], label=f"{row['instrument']} qty_end"),
                price_start=_decimal(row["price_start"], label=f"{row['instrument']} price_start"),
                price_end=_decimal(row["price_end"], label=f"{row['instrument']} price_end"),
                reported_pnl=(
                    _decimal(row["reported_pnl"], label=f"{row['instrument']} reported_pnl")
                    if row.get("reported_pnl")
                    else None
                ),
            )
            for row in position_rows
        ],
        [
            FactorReturn(
                factor=row["factor"],
                simple_return=_decimal(row["simple_return"], label=f"{row['factor']} simple_return"),
            )
            for row in factor_rows
        ],
        [
            Loading(
                instrument=row["instrument"],
                factor=row["factor"],
                beta=_decimal(row["beta"], label=f"{row['instrument']} {row['factor']} beta"),
            )
            for row in loading_rows
        ],
        session=session,
    )


def make_book(
    positions: Sequence[Position],
    factors: Sequence[FactorReturn],
    loadings: Sequence[Loading],
    *,
    session: str = SAMPLE_SESSION,
    currency: str = "USD",
) -> Book:
    """Validate a snapshot and store decimals.

    Integers are accepted and converted. Binary floats are rejected.
    """
    label = _session_label(session)
    if currency != "USD":
        raise PnlAttributionError("prices are USD amounts; this demo does not convert currencies")
    if not positions:
        raise PnlAttributionError("at least one instrument is required")
    if not factors:
        raise PnlAttributionError("at least one factor is required")

    clean_positions: list[Position] = []
    seen_instruments: set[str] = set()
    for position in positions:
        name = _token(position.instrument, label="instrument")
        if name in seen_instruments:
            raise PnlAttributionError(f"duplicate instrument {name}")
        seen_instruments.add(name)
        price_start = _as_decimal(position.price_start, label=f"{name} price_start")
        price_end = _as_decimal(position.price_end, label=f"{name} price_end")
        if price_start <= 0:
            raise PnlAttributionError(f"{name} price_start must be positive")
        if price_end <= 0:
            raise PnlAttributionError(f"{name} price_end must be positive")
        reported = position.reported_pnl
        clean_positions.append(
            Position(
                instrument=name,
                qty_start=_as_decimal(position.qty_start, label=f"{name} qty_start"),
                qty_end=_as_decimal(position.qty_end, label=f"{name} qty_end"),
                price_start=price_start,
                price_end=price_end,
                reported_pnl=(
                    None
                    if reported is None
                    else _as_decimal(reported, label=f"{name} reported_pnl")
                ),
            )
        )

    clean_factors: list[FactorReturn] = []
    seen_factors: set[str] = set()
    for factor in factors:
        name = _token(factor.factor, label="factor")
        if name in seen_factors:
            raise PnlAttributionError(f"duplicate factor {name}")
        seen_factors.add(name)
        clean_factors.append(
            FactorReturn(
                factor=name,
                simple_return=_as_decimal(factor.simple_return, label=f"{name} simple_return"),
            )
        )

    clean_loadings: list[Loading] = []
    seen_loadings: set[tuple[str, str]] = set()
    for loading in loadings:
        instrument = _token(loading.instrument, label="loading instrument")
        factor = _token(loading.factor, label="loading factor")
        if instrument not in seen_instruments:
            raise PnlAttributionError(f"loading for unknown instrument {instrument}")
        if factor not in seen_factors:
            raise PnlAttributionError(f"loading for unknown factor {factor}")
        key = (instrument, factor)
        if key in seen_loadings:
            raise PnlAttributionError(f"duplicate loading for {instrument} on {factor}")
        seen_loadings.add(key)
        clean_loadings.append(
            Loading(
                instrument=instrument,
                factor=factor,
                beta=_as_decimal(loading.beta, label=f"{instrument} {factor} beta"),
            )
        )

    return Book(
        positions=tuple(clean_positions),
        factors=tuple(clean_factors),
        loadings=tuple(clean_loadings),
        session=label,
        currency=currency,
    )


def _bundled(filename: str) -> Path:
    path = Path(__file__).resolve().parents[2] / "data" / filename
    if not path.is_file():
        raise PnlAttributionError(
            f"could not find data/{filename}. Pass the CSV paths explicitly."
        )
    return path


def _read_table(
    path: Path,
    *,
    required: tuple[str, ...],
    optional: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    if not path.is_file():
        raise PnlAttributionError(f"file not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, restkey="__extra__", restval="")
        if not reader.fieldnames:
            raise PnlAttributionError(f"file is empty: {path}")
        fieldnames = [(name or "").strip().lower() for name in reader.fieldnames]
        if any(not name for name in fieldnames):
            raise PnlAttributionError(f"{path.name} has a blank column name")
        if len(fieldnames) != len(set(fieldnames)):
            raise PnlAttributionError(f"{path.name} has a duplicate column name")
        reader.fieldnames = fieldnames
        allowed = set(required) | set(optional)
        missing = [name for name in required if name not in fieldnames]
        unknown = [name for name in fieldnames if name not in allowed]
        if missing:
            raise PnlAttributionError(f"{path.name} is missing column(s): {', '.join(missing)}")
        if unknown:
            raise PnlAttributionError(f"{path.name} has unexpected column(s): {', '.join(unknown)}")
        present = tuple(name for name in (*required, *optional) if name in fieldnames)
        rows: list[dict[str, str]] = []
        for row_number, raw in enumerate(reader, start=1):
            extra = raw.get("__extra__")
            if extra and any(cell.strip() for cell in extra):
                raise PnlAttributionError(f"{path.name} row {row_number} has too many columns")
            values = {key: (raw.get(key) or "").strip() for key in present}
            if not any(values.get(key) for key in required):
                continue
            blank = [key for key in required if not values.get(key)]
            if blank:
                raise PnlAttributionError(
                    f"{path.name} row {row_number} is missing {', '.join(blank)}"
                )
            rows.append(values)
    return rows


def _session_label(session: str) -> str:
    if not isinstance(session, str):
        raise PnlAttributionError("session label must be a string")
    label = session.strip()
    if not label or any(char.isspace() for char in label):
        raise PnlAttributionError("session label must be a single non-empty token")
    return label


def _token(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise PnlAttributionError(f"{label} must be a string")
    name = value.strip()
    if not name:
        raise PnlAttributionError(f"{label} is blank")
    if any(char.isspace() for char in name):
        raise PnlAttributionError(f"{label} {name!r} cannot contain whitespace")
    return name


def _decimal(text: str, *, label: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise PnlAttributionError(f"{label} is not a number") from exc
    if not value.is_finite():
        raise PnlAttributionError(f"{label} is not finite")
    return value


def _as_decimal(value: Decimal | int, *, label: str) -> Decimal:
    # bool is a subclass of int. A quantity of True is not a position.
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise PnlAttributionError(f"{label} must be a Decimal or an int")
    if isinstance(value, int):
        return Decimal(value)
    if not value.is_finite():
        raise PnlAttributionError(f"{label} is not finite")
    return value


def betas_by_instrument(book: Book) -> dict[str, tuple[Loading, ...]]:
    """Loadings grouped by instrument, in file order."""
    grouped: dict[str, list[Loading]] = {position.instrument: [] for position in book.positions}
    for loading in book.loadings:
        grouped[loading.instrument].append(loading)
    return {name: tuple(items) for name, items in grouped.items()}
