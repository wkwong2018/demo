"""Text report for one demo run."""

from __future__ import annotations

from risk_lake.pipeline import DemoResult


def format_report(result: DemoResult) -> str:
    """Return the full text report, including a trailing newline."""
    snapshot = result.snapshot
    lines: list[str] = [
        f"market-risk-streaming-lake {result.version}",
        "Synthetic streaming ingest, medallion lake, and book limit monitor",
        "",
        (
            f"Sessions: {result.session_start} to {result.session_end} "
            f"({result.session_count} weekdays)"
        ),
        (
            "Events: "
            f"{result.event_counts['market_factor']} market factors, "
            f"{result.event_counts['position']} positions, "
            f"{result.event_counts['pnl']} pnl"
        ),
        f"Bus: {result.bus}",
        "Topics: " + ", ".join(result.topics),
        f"Lake: {result.lake_display}",
        f"Sibling price index: {result.sibling_prices_display}",
        (
            f"Limits scored on {snapshot.as_of}. "
            f"Historical VaR and ES use the last {snapshot.var_window} daily P&L amounts "
            f"at {snapshot.confidence:.2%} confidence, equal weight, Hyndman-Fan type 7."
        ),
        "P&L is signed, gain positive. VaR, ES, and daily loss are loss amounts.",
        "A breach is value > limit. ES is shown and is not a configured limit.",
        f"Explainer: {result.explainer_name}.",
        "",
        _table(snapshot.rows, confidence=snapshot.confidence),
        "",
    ]
    observations = int(snapshot.rows["var_observations"].iloc[0]) if not snapshot.rows.empty else 0
    expected_tail = observations * (1.0 - snapshot.confidence)
    lines.append(
        f"The VaR window has {observations} observations and about {expected_tail:.1f} "
        "expected tail points at this confidence, so the historical quantile is coarse."
    )
    if observations < snapshot.var_window:
        lines.append(
            f"The configured window is {snapshot.var_window}, and only {observations} "
            "P&L sessions were available."
        )
    lines.append("")
    if snapshot.breaches:
        lines.append(f"Breaches: {len(snapshot.breaches)}")
        for breach in snapshot.breaches:
            lines.append(
                f"- {breach.desk} / {breach.book} {breach.metric_label}: "
                f"{_amount(breach.value)} against {_amount(breach.limit)} "
                f"({breach.utilization * 100:.1f}% of limit)"
            )
    else:
        lines.append("Breaches: 0")
        lines.append("No configured limit was breached on the latest session.")
    lines.append("")
    if result.explanation is not None:
        lines.append(f"Sample explanation ({result.explainer_name}, not a model decision):")
        lines.append(result.explanation)
    else:
        lines.append("Sample explanation: none, because no limit was breached.")
    lines.append("")
    lines.append(
        "Personal interview demo. Not a production risk system. "
        "Not investment advice. Not affiliated with any employer."
    )
    return "\n".join(lines) + "\n"


def _table(rows, *, confidence: float) -> str:
    percent = f"{confidence * 100:.0f}"
    header = (
        f"{'Desk':<12} {'Book':<20} {'Notional':>14} {'Util':>7} "
        f"{'Daily loss':>14} {'Util':>7} {('VaR ' + percent):>14} {'Util':>7} "
        f"{('ES ' + percent):>14} {'Status':<8}"
    )
    body = [header]
    for row in rows.itertuples(index=False):
        body.append(
            f"{row.desk:<12} {row.book:<20} {_amount(row.gross_notional):>14} "
            f"{_util(row.notional_utilization):>7} {_amount(row.daily_loss):>14} "
            f"{_util(row.daily_loss_utilization):>7} {_amount(row.var_loss):>14} "
            f"{_util(row.var_utilization):>7} {_amount(row.es_loss):>14} {row.status:<8}"
        )
    return "\n".join(body)


def _amount(value: float) -> str:
    return f"{value:,.2f}"


def _util(value: float) -> str:
    return f"{value * 100:.1f}%"
