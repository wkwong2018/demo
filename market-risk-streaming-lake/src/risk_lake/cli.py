"""Command-line entry point for the streaming demo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from risk_lake.errors import RiskLakeError
from risk_lake.limits import default_limits_path
from risk_lake.pipeline import DemoRequest, run_demo
from risk_lake.report import format_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="risk-lake",
        description=(
            "Stream synthetic market-risk events into a bronze/silver/gold lake, "
            "score book limits, and print one breach explanation."
        ),
    )
    sub = parser.add_subparsers(dest="command")
    demo = sub.add_parser("demo", help="Run the in-process demo, or Kafka when --bus kafka is set.")
    demo.add_argument("--sessions", type=int, default=60, help="Weekday sessions to generate. Default: 60.")
    demo.add_argument("--seed", type=int, default=7, help="Generator seed. Default: 7.")
    demo.add_argument(
        "--lake",
        type=Path,
        default=Path("lake"),
        help="Local lake root. Bronze, silver, and gold under this path are replaced. Default: ./lake",
    )
    demo.add_argument(
        "--limits",
        type=Path,
        default=None,
        help="YAML limit file. Default: config/limits.yml in the project directory.",
    )
    demo.add_argument(
        "--bus",
        choices=("memory", "kafka"),
        default="memory",
        help="memory runs with no broker. kafka expects a running Apache Kafka. Default: memory.",
    )
    demo.add_argument(
        "--bootstrap-servers",
        default=None,
        help="Kafka bootstrap servers. Default: KAFKA_BOOTSTRAP_SERVERS or localhost:9092.",
    )
    demo.add_argument(
        "--explainer",
        choices=("template", "openai"),
        default="template",
        help="template is offline. openai is used only when this flag is set and OPENAI_API_KEY is present.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the demo. Returns 0 on success and 1 on a data or runtime error."""
    parser = build_parser()
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list:
        args_list = ["demo"]
    args = parser.parse_args(args_list)
    if args.command != "demo":
        parser.print_help(sys.stderr)
        return 2
    try:
        limits = args.limits if args.limits is not None else default_limits_path()
        result = run_demo(
            DemoRequest(
                sessions=args.sessions,
                seed=args.seed,
                lake=args.lake,
                limits=limits,
                bus=args.bus,
                bootstrap_servers=args.bootstrap_servers,
                explainer=args.explainer,
            )
        )
    except RiskLakeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(format_report(result), end="")
    return 0
