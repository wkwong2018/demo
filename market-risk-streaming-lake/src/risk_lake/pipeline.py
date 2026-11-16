"""End-to-end batch: generate, publish, land, score, explain.

The demo is one shot. It writes every event, reads the bronze parquet back,
builds silver and gold, and returns the text-report inputs. It does not
leave a consumer running.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from risk_lake.bus import build_bus
from risk_lake.errors import RiskLakeError
from risk_lake.events import TOPIC_MARKET_FACTORS, TOPIC_PNL, TOPIC_POSITIONS, TOPICS
from risk_lake.explain import Explainer, build_explainer
from risk_lake.lake import LakeWriter, LocalLakeWriter
from risk_lake.limits import RiskSnapshot, book_panel, build_snapshot, load_limits, sibling_price_frame
from risk_lake.streaming import EventConsumer, EventProducer
from risk_lake.synthetic import generate_events
from risk_lake.transform import to_silver
from risk_lake.version import __version__


@dataclass(frozen=True)
class DemoRequest:
    """Inputs for one local or Kafka run."""

    sessions: int = 60
    seed: int = 7
    lake: Path = Path("lake")
    limits: Path | None = None
    bus: str = "memory"
    bootstrap_servers: str | None = None
    explainer: str = "template"


@dataclass(frozen=True)
class DemoResult:
    """What the text report needs after a successful run."""

    version: str
    bus: str
    lake: Path
    lake_display: str
    sibling_prices_display: str
    session_start: str
    session_end: str
    session_count: int
    event_counts: dict[str, int]
    snapshot: RiskSnapshot
    explanation: str | None
    explainer_name: str
    sibling_prices: Path
    topics: tuple[str, ...]


def run_demo(request: DemoRequest, explainer: Explainer | None = None) -> DemoResult:
    """Run the batch and return the report inputs."""
    if request.sessions < 2:
        raise RiskLakeError("sessions must be at least 2")
    limits_path = request.limits if request.limits is not None else _limits_from_request()
    config = load_limits(limits_path)
    events = generate_events(sessions=request.sessions, seed=request.seed)
    lake = _prepare_lake(request.lake)
    writer = LocalLakeWriter(lake)

    bus = build_bus(request.bus, request.bootstrap_servers)
    try:
        published = EventProducer(bus).publish(events)
        landed = EventConsumer(bus).read(TOPICS)
    finally:
        bus.close()
    if published != len(events):
        raise RiskLakeError("the producer did not accept every event")
    if sum(len(rows) for rows in landed.values()) != published:
        raise RiskLakeError("the consumer did not read every published event")

    _write_bronze(writer, landed)
    silver = to_silver(
        writer.read_dataset("bronze", "market-factors").to_dict(orient="records"),
        writer.read_dataset("bronze", "positions").to_dict(orient="records"),
        writer.read_dataset("bronze", "pnl").to_dict(orient="records"),
    )
    if silver.rejected:
        sample = silver.rejected[0]
        raise RiskLakeError(
            f"silver rejected {len(silver.rejected)} rows. "
            f"First: {sample.event_id or 'unknown'} ({sample.reason})"
        )
    _write_partitioned(writer, "silver", "market-factors", silver.market_factors)
    _write_partitioned(writer, "silver", "positions", silver.positions)
    _write_partitioned(writer, "silver", "pnl", silver.pnl)

    panel = book_panel(silver.positions, silver.pnl)
    snapshot = build_snapshot(panel, config)
    _write_gold(writer, snapshot, panel)
    prices = sibling_price_frame(panel, config)
    sibling_path = Path(
        writer.write_table(
            "gold",
            "sibling-prices",
            prices,
            file_name="prices.csv",
        )
    )
    chosen = explainer if explainer is not None else build_explainer(request.explainer)
    explanation = chosen.explain(snapshot.breaches[0]) if snapshot.breaches else None
    counts = {
        "market_factor": int(silver.market_factors.shape[0]),
        "position": int(silver.positions.shape[0]),
        "pnl": int(silver.pnl.shape[0]),
    }
    return DemoResult(
        version=__version__,
        bus=request.bus,
        lake=lake,
        lake_display=_display_path(request.lake, lake, lake),
        sibling_prices_display=_display_path(request.lake, lake, sibling_path),
        session_start=str(panel["session_date"].iloc[0]),
        session_end=str(panel["session_date"].iloc[-1]),
        session_count=int(panel["session_date"].nunique()),
        event_counts=counts,
        snapshot=snapshot,
        explanation=explanation,
        explainer_name=chosen.name,
        sibling_prices=sibling_path,
        topics=TOPICS,
    )


def _display_path(requested: Path, root: Path, actual: Path) -> str:
    """Show the caller's path when it is relative, and the real path otherwise."""
    try:
        relative = actual.resolve().relative_to(root)
    except ValueError:
        return str(actual)
    base = requested if requested.is_absolute() else Path(requested)
    if relative == Path("."):
        return str(base)
    return str(base / relative)


def _limits_from_request() -> Path:
    from risk_lake.limits import default_limits_path

    return default_limits_path()


def _prepare_lake(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    if resolved == Path("/") or resolved == Path.home():
        raise RiskLakeError("refusing to use this lake path")
    resolved.mkdir(parents=True, exist_ok=True)
    for layer in ("bronze", "silver", "gold"):
        target = resolved / layer
        if target.exists():
            shutil.rmtree(target)
    return resolved


def _write_bronze(writer: LakeWriter, landed: dict[str, list[dict[str, object]]]) -> None:
    _write_partitioned(writer, "bronze", "market-factors", _frame(landed[TOPIC_MARKET_FACTORS]))
    _write_partitioned(writer, "bronze", "positions", _frame(landed[TOPIC_POSITIONS]))
    _write_partitioned(writer, "bronze", "pnl", _frame(landed[TOPIC_PNL]))


def _write_partitioned(writer: LakeWriter, layer: str, dataset: str, frame: pd.DataFrame) -> None:
    if frame.empty:
        raise RiskLakeError(f"{layer}/{dataset} has no rows")
    for session_date, part in frame.groupby("session_date", sort=True):
        writer.write_table(
            layer,
            dataset,
            part.reset_index(drop=True),
            partition={"date": str(session_date)},
        )


def _write_gold(writer: LakeWriter, snapshot: RiskSnapshot, panel: pd.DataFrame) -> None:
    writer.write_table(
        "gold",
        "book-daily",
        panel,
        file_name="part-000.parquet",
    )
    writer.write_table(
        "gold",
        "risk-report",
        snapshot.rows,
        partition={"date": snapshot.as_of},
    )
    breach_frame = _breach_frame(snapshot)
    writer.write_table(
        "gold",
        "limit-breaches",
        breach_frame,
        partition={"date": snapshot.as_of},
    )


def _breach_frame(snapshot: RiskSnapshot) -> pd.DataFrame:
    columns = [
        "session_date",
        "desk",
        "book",
        "metric",
        "metric_label",
        "value",
        "limit",
        "utilization",
        "currency",
    ]
    if not snapshot.breaches:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame([item.__dict__ for item in snapshot.breaches], columns=columns)


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)
