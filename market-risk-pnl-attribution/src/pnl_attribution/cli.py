"""Command-line entry point for the session P&L report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from pnl_attribution.book import (
    SAMPLE_SESSION,
    bundled_factors_path,
    bundled_loadings_path,
    bundled_positions_path,
    load_book,
)
from pnl_attribution.errors import PnlAttributionError
from pnl_attribution.explain import explain_book
from pnl_attribution.report import format_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pnl-attribution",
        description=(
            "Explain one session of linear P&L: market move versus quantity change, "
            "then a stated-beta factor split of the market piece."
        ),
        epilog=(
            "Example: pnl-attribution --positions positions.csv "
            "--factors factors.csv --loadings loadings.csv"
        ),
    )
    parser.add_argument(
        "--positions",
        type=Path,
        default=None,
        help=(
            "CSV of instrument, qty_start, qty_end, price_start, price_end, "
            "and optional reported_pnl. Default: the synthetic snapshot."
        ),
    )
    parser.add_argument(
        "--factors",
        type=Path,
        default=None,
        help="CSV of factor, simple_return. Default: the synthetic factor file.",
    )
    parser.add_argument(
        "--loadings",
        type=Path,
        default=None,
        help="CSV of instrument, factor, beta. Default: the synthetic loadings.",
    )
    parser.add_argument(
        "--session",
        default=SAMPLE_SESSION,
        help=(
            "Label printed on the report. It does not change the P&L. "
            f"Default: {SAMPLE_SESSION}."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report. Returns 0 on success and 1 on a data error."""
    parser = build_parser()
    args = parser.parse_args(None if argv is None else list(argv))
    try:
        book = load_book(
            args.positions if args.positions is not None else bundled_positions_path(),
            args.factors if args.factors is not None else bundled_factors_path(),
            args.loadings if args.loadings is not None else bundled_loadings_path(),
            session=args.session,
        )
        result = explain_book(book)
    except PnlAttributionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(format_report(result), end="")
    return 0
