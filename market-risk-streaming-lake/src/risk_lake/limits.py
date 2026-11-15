"""Book limits and the latest-session utilization snapshot.

This is a limit-monitoring illustration. It compares three numbers on the
latest session with the thresholds in ``config/limits.yml``:

- gross notional, the sum of absolute instrument notionals
- daily loss, ``max(-daily P&L, 0)``
- one-day historical VaR on the trailing P&L window

A metric breaches when its value is strictly greater than its limit.
Expected Shortfall is computed and stored. It is not itself a limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pandas as pd
import yaml

from risk_lake.errors import RiskLakeError
from risk_lake.measures import historical_es_loss, historical_var_loss, validate_confidence

_METRIC_LABELS = {
    "gross_notional": "gross notional",
    "daily_loss": "daily loss",
    "historical_var": "historical VaR",
}


@dataclass(frozen=True)
class BookLimit:
    """Thresholds for one book, in the report currency."""

    desk: str
    book: str
    index_name: str
    notional: float
    daily_loss: float
    var: float


@dataclass(frozen=True)
class LimitConfig:
    """The file the demo scores against."""

    currency: str
    confidence: float
    var_window: int
    books: tuple[BookLimit, ...]

    def for_book(self, desk: str, book: str) -> BookLimit:
        for item in self.books:
            if item.desk == desk and item.book == book:
                return item
        raise RiskLakeError(f"no limit configured for {desk} / {book}")


@dataclass(frozen=True)
class LimitBreach:
    """One metric on one book that finished above its limit."""

    session_date: str
    desk: str
    book: str
    metric: str
    metric_label: str
    value: float
    limit: float
    utilization: float
    currency: str


@dataclass(frozen=True)
class RiskSnapshot:
    """Gold-layer limit report for the latest session in the panel."""

    as_of: str
    rows: pd.DataFrame
    breaches: tuple[LimitBreach, ...]
    confidence: float
    var_window: int


def default_limits_path() -> Path:
    """Find ``config/limits.yml`` from the working directory or the checkout."""
    cwd_candidate = Path("config") / "limits.yml"
    if cwd_candidate.is_file():
        return cwd_candidate.resolve()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config" / "limits.yml"
        if candidate.is_file():
            return candidate
    raise RiskLakeError(
        "could not find config/limits.yml. Pass --limits, or run from the project directory."
    )


def load_limits(path: str | Path) -> LimitConfig:
    """Load and validate the limit file."""
    file_path = Path(path)
    if not file_path.is_file():
        raise RiskLakeError(f"limits file not found: {file_path}")
    try:
        loaded = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RiskLakeError(f"limits file is not valid YAML: {file_path}") from exc
    if not isinstance(loaded, dict):
        raise RiskLakeError("limits file must be a mapping")
    return _parse_config(loaded)


def book_panel(positions: pd.DataFrame, pnl: pd.DataFrame) -> pd.DataFrame:
    """Sum instrument notionals and P&L to one row per book and session."""
    _require_columns(positions, {"session_date", "desk", "book", "notional"}, "positions")
    _require_columns(pnl, {"session_date", "desk", "book", "pnl"}, "pnl")
    if positions.empty or pnl.empty:
        raise RiskLakeError("positions and pnl are both required")
    keys = ["session_date", "desk", "book"]
    notionals = positions.groupby(keys, as_index=False)["notional"].sum()
    pnls = pnl.groupby(keys, as_index=False)["pnl"].sum()
    panel = notionals.merge(pnls, on=keys, how="outer", sort=False)
    if panel[["notional", "pnl"]].isna().any().any():
        raise RiskLakeError("a book session is missing notional or pnl")
    panel = panel.sort_values(keys, kind="mergesort").reset_index(drop=True)
    panel["notional"] = panel["notional"].astype(float)
    panel["pnl"] = panel["pnl"].astype(float)
    return panel


def build_snapshot(panel: pd.DataFrame, config: LimitConfig) -> RiskSnapshot:
    """Score each configured book on the latest session in ``panel``."""
    if panel.empty:
        raise RiskLakeError("the book panel is empty")
    seen = {(str(row.desk), str(row.book)) for row in panel.itertuples(index=False)}
    configured = {(item.desk, item.book) for item in config.books}
    missing = sorted(configured - seen)
    extra = sorted(seen - configured)
    if missing or extra:
        raise RiskLakeError(
            "limits must cover the books in the lake exactly. "
            f"Missing {missing or 'none'}. Unexpected {extra or 'none'}."
        )

    rows: list[dict[str, object]] = []
    breaches: list[LimitBreach] = []
    as_of = ""
    for item in config.books:
        history = panel[(panel["desk"] == item.desk) & (panel["book"] == item.book)]
        history = history.sort_values("session_date", kind="mergesort")
        latest = history.iloc[-1]
        session_date = str(latest["session_date"])
        if as_of and session_date != as_of:
            raise RiskLakeError("books do not share a latest session")
        as_of = session_date
        window = history["pnl"].to_numpy(dtype=float)[-config.var_window :]
        var_loss = historical_var_loss(window, config.confidence)
        es_loss = historical_es_loss(window, config.confidence)
        gross_notional = float(latest["notional"])
        daily_pnl = float(latest["pnl"])
        signed_loss = -daily_pnl
        # A gain, or a P&L that rounds to zero, is not a loss. Avoid -0.0.
        daily_loss = signed_loss if signed_loss > 0.0 else 0.0
        metrics = (
            ("gross_notional", gross_notional, item.notional),
            ("daily_loss", daily_loss, item.daily_loss),
            ("historical_var", var_loss, item.var),
        )
        flags: dict[str, bool] = {}
        utils: dict[str, float] = {}
        for metric, value, limit in metrics:
            utilization = value / limit
            breach = value > limit
            utils[metric] = utilization
            flags[metric] = breach
            if breach:
                breaches.append(
                    LimitBreach(
                        session_date=session_date,
                        desk=item.desk,
                        book=item.book,
                        metric=metric,
                        metric_label=_METRIC_LABELS[metric],
                        value=value,
                        limit=limit,
                        utilization=utilization,
                        currency=config.currency,
                    )
                )
        rows.append(
            {
                "session_date": session_date,
                "desk": item.desk,
                "book": item.book,
                "currency": config.currency,
                "gross_notional": gross_notional,
                "notional_limit": item.notional,
                "notional_utilization": utils["gross_notional"],
                "notional_breach": flags["gross_notional"],
                "daily_pnl": daily_pnl,
                "daily_loss": daily_loss,
                "daily_loss_limit": item.daily_loss,
                "daily_loss_utilization": utils["daily_loss"],
                "daily_loss_breach": flags["daily_loss"],
                "var_loss": var_loss,
                "var_limit": item.var,
                "var_utilization": utils["historical_var"],
                "var_breach": flags["historical_var"],
                "es_loss": es_loss,
                "var_observations": int(window.size),
                "var_window": config.var_window,
                "confidence": config.confidence,
                "status": "breach" if any(flags.values()) else "inside",
            }
        )

    ordered = tuple(
        sorted(breaches, key=lambda item: (-item.utilization, item.desk, item.book, item.metric))
    )
    frame = pd.DataFrame(rows)
    return RiskSnapshot(
        as_of=as_of,
        rows=frame,
        breaches=ordered,
        confidence=config.confidence,
        var_window=config.var_window,
    )


def sibling_price_frame(panel: pd.DataFrame, config: LimitConfig) -> pd.DataFrame:
    """Rebuild a positive price index from book P&L returns.

    The index starts at 100 on the first session. From the second session,

        r_t = pnl_t / notional_(t-1)
        P_t = P_(t-1) * (1 + r_t)

    The first session's P&L is the base and is not a return. Prices are
    rounded to 6 decimal places. The sibling project can read the resulting
    CSV as a price file; this function does not import it.
    """
    columns: dict[str, list[object]] = {"date": []}
    dates: list[str] | None = None
    for item in config.books:
        history = panel[(panel["desk"] == item.desk) & (panel["book"] == item.book)]
        history = history.sort_values("session_date", kind="mergesort")
        session_dates = [str(value) for value in history["session_date"]]
        if dates is None:
            dates = session_dates
        elif session_dates != dates:
            raise RiskLakeError("books must share the same session dates for the price index")
        levels = _price_index(
            history["pnl"].to_numpy(dtype=float),
            history["notional"].to_numpy(dtype=float),
            name=item.book,
        )
        columns[item.index_name] = levels
    if dates is None:
        raise RiskLakeError("no books to export")
    columns["date"] = dates
    ordered = ["date", *[item.index_name for item in config.books]]
    return pd.DataFrame(columns)[ordered]


def _price_index(pnl, notional, *, name: str) -> list[float]:
    if len(pnl) < 2:
        raise RiskLakeError(f"{name} needs at least two sessions for a price index")
    levels = [100.0]
    for index in range(1, len(pnl)):
        base = float(notional[index - 1])
        if base <= 0.0:
            raise RiskLakeError(f"{name} has a non-positive notional before a return")
        updated = levels[-1] * (1.0 + float(pnl[index]) / base)
        if updated <= 0.0:
            raise RiskLakeError(f"{name} price index would not stay positive")
        levels.append(round(updated, 6))
    return levels


def _parse_config(loaded: Mapping[str, object]) -> LimitConfig:
    currency = loaded.get("currency")
    if currency != "USD":
        raise RiskLakeError("this demo limits file uses currency USD")
    confidence = validate_confidence(_required_float(loaded.get("confidence"), "confidence"))
    window_raw = loaded.get("var_window")
    if isinstance(window_raw, bool) or not isinstance(window_raw, int) or window_raw < 2:
        raise RiskLakeError("var_window must be an integer of at least 2")
    books_raw = loaded.get("books")
    if not isinstance(books_raw, list) or not books_raw:
        raise RiskLakeError("limits file needs at least one book")
    books: list[BookLimit] = []
    seen: set[tuple[str, str]] = set()
    index_names: set[str] = set()
    for entry in books_raw:
        if not isinstance(entry, dict):
            raise RiskLakeError("each book limit must be a mapping")
        desk = _token(entry.get("desk"), "desk")
        book = _token(entry.get("book"), "book")
        index_name = _token(entry.get("index_name"), "index_name")
        if (desk, book) in seen:
            raise RiskLakeError(f"duplicate limit for {desk} / {book}")
        if index_name in index_names:
            raise RiskLakeError(f"duplicate index name {index_name}")
        seen.add((desk, book))
        index_names.add(index_name)
        books.append(
            BookLimit(
                desk=desk,
                book=book,
                index_name=index_name,
                notional=_positive(entry.get("notional"), "notional"),
                daily_loss=_positive(entry.get("daily_loss"), "daily_loss"),
                var=_positive(entry.get("var"), "var"),
            )
        )
    return LimitConfig(
        currency="USD",
        confidence=confidence,
        var_window=window_raw,
        books=tuple(books),
    )


def _token(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RiskLakeError(f"{name} is required")
    return value.strip()


def _required_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RiskLakeError(f"{name} must be a number")
    return float(value)


def _positive(value: object, name: str) -> float:
    number = _required_float(value, name)
    if number <= 0.0:
        raise RiskLakeError(f"{name} must be positive")
    return number


def _require_columns(frame: pd.DataFrame, columns: set[str], name: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise RiskLakeError(f"{name} is missing columns {missing}")
