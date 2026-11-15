"""Command-line entry point for the sample VaR / ES report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from market_risk.analysis import run_analysis
from market_risk.errors import MarketRiskError
from market_risk.portfolio import SAMPLE_WEIGHTS, bundled_sample_prices_path, load_prices
from market_risk.report import format_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="market-risk",
        description=(
            "Compute one-day historical and parametric VaR, Expected Shortfall, "
            "and Kupiec / Christoffersen backtests for a constant-weight portfolio."
        ),
        epilog=(
            "Example: market-risk --confidence 0.99 --window 250 "
            "--weights SPY=0.35,EFA=0.20,EEM=0.10,AGG=0.25,GLD=0.10"
        ),
    )
    parser.add_argument(
        "--prices",
        type=Path,
        default=None,
        help="CSV of positive prices with a date column. Default: the recorded ETF sample.",
    )
    parser.add_argument(
        "--weights",
        default=None,
        help=(
            "Comma-separated ticker=weight pairs that sum to 1. "
            "Default: SPY=0.35,EFA=0.20,EEM=0.10,AGG=0.25,GLD=0.10."
        ),
    )
    parser.add_argument(
        "--confidence",
        action="append",
        dest="confidences",
        type=float,
        default=None,
        help="Loss confidence in (0, 1). Repeat to print several. Default: 0.95 and 0.99.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=250,
        help="Number of past sessions in the current estimate and in each forecast. Default: 250.",
    )
    parser.add_argument(
        "--portfolio-value",
        type=float,
        default=1_000_000.0,
        help="Portfolio value used to scale loss fractions into amounts. Default: 1000000.",
    )
    parser.add_argument(
        "--significance",
        type=float,
        default=0.05,
        help="Size of the coverage tests. Default: 0.05.",
    )
    parser.add_argument(
        "--zero-mean",
        action="store_true",
        help="Force the Gaussian location to 0. Historical VaR and ES are unchanged.",
    )
    return parser


def parse_weights(text: str) -> dict[str, float]:
    """Parse ``SPY=0.35,AGG=0.25`` into a weight map."""
    weights: dict[str, float] = {}
    for part in text.split(","):
        piece = part.strip()
        if not piece:
            continue
        if "=" not in piece:
            raise MarketRiskError(f"weight {piece!r} must look like SPY=0.35")
        ticker, raw = piece.split("=", 1)
        name = ticker.strip().upper()
        if not name:
            raise MarketRiskError(f"weight {piece!r} is missing a ticker")
        if name in weights:
            raise MarketRiskError(f"duplicate weight for {name}")
        try:
            weights[name] = float(raw.strip())
        except ValueError as exc:
            raise MarketRiskError(f"weight for {name} is not a number") from exc
    if not weights:
        raise MarketRiskError("at least one weight is required")
    return weights


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report. Returns 0 on success and 1 on a data or model error."""
    parser = build_parser()
    args = parser.parse_args(None if argv is None else list(argv))
    try:
        prices = load_prices(args.prices if args.prices is not None else bundled_sample_prices_path())
        weights = parse_weights(args.weights) if args.weights is not None else dict(SAMPLE_WEIGHTS)
        confidences = args.confidences if args.confidences is not None else (0.95, 0.99)
        result = run_analysis(
            prices,
            weights,
            portfolio_value=args.portfolio_value,
            confidences=confidences,
            window=args.window,
            zero_mean=args.zero_mean,
            significance=args.significance,
        )
    except MarketRiskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(format_report(result), end="")
    return 0
