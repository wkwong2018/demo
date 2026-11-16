"""In-process demo, with no broker and no network."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from risk_lake.cli import main
from risk_lake.pipeline import DemoRequest, run_demo


def test_demo_lands_a_lake_and_breaches_the_equity_book(tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    result = run_demo(
        DemoRequest(
            sessions=60,
            seed=7,
            lake=lake,
            limits=Path(__file__).resolve().parents[1] / "config" / "limits.yml",
        )
    )
    equity = result.snapshot.rows.loc[result.snapshot.rows["desk"] == "EQ-DELTA-1"].iloc[0]
    others = result.snapshot.rows.loc[result.snapshot.rows["desk"] != "EQ-DELTA-1"]

    assert equity["notional_breach"]
    assert equity["daily_loss_breach"]
    assert not bool(equity["var_breach"])
    assert equity["status"] == "breach"
    assert equity["daily_loss"] > equity["daily_loss_limit"]
    assert not others["notional_breach"].any()
    assert not others["daily_loss_breach"].any()
    assert not others["var_breach"].any()
    assert (others["status"] == "inside").all()

    assert result.explainer_name == "template"
    assert result.explanation is not None
    assert "EQ-DELTA-1" in result.explanation
    assert "not the decision" in result.explanation

    bronze = lake / "bronze" / "market-factors" / f"date={result.session_start}" / "part-000.parquet"
    silver = lake / "silver" / "pnl" / f"date={result.session_end}" / "part-000.parquet"
    gold = lake / "gold" / "risk-report" / f"date={result.snapshot.as_of}" / "part-000.parquet"
    assert bronze.is_file()
    assert silver.is_file()
    assert gold.is_file()
    assert (lake / "gold" / "limit-breaches" / f"date={result.snapshot.as_of}" / "part-000.parquet").is_file()

    prices = pd.read_csv(result.sibling_prices)
    assert list(prices.columns) == ["date", "SYN-EQ", "SYN-FI", "SYN-FX"]
    assert (prices[["SYN-EQ", "SYN-FI", "SYN-FX"]] > 0).all().all()
    assert prices.iloc[0]["SYN-EQ"] == 100


def test_cli_prints_the_disclaimer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(
        [
            "demo",
            "--lake",
            str(tmp_path / "lake"),
            "--limits",
            str(Path(__file__).resolve().parents[1] / "config" / "limits.yml"),
            "--sessions",
            "60",
            "--seed",
            "7",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Not a production risk system" in captured.out
    assert "Not affiliated with any employer" in captured.out
    assert "Breaches:" in captured.out
    assert captured.err == ""


def test_cli_reports_a_missing_limit_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["demo", "--lake", str(tmp_path / "lake"), "--limits", str(tmp_path / "missing.yml")])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "limits file not found" in captured.err
