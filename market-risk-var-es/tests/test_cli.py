"""CLI smoke tests and the scoped GitHub Actions workflow."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_risk import __version__
from market_risk.cli import main, parse_weights
from market_risk.errors import MarketRiskError
from market_risk.report import format_report


def test_parse_weights_is_tolerant_of_spacing_and_case():
    assert parse_weights(" spy=0.4, agg=0.6 ") == {"SPY": 0.4, "AGG": 0.6}
    with pytest.raises(MarketRiskError):
        parse_weights("SPY")
    with pytest.raises(MarketRiskError):
        parse_weights("SPY=weight")


def test_cli_prints_a_backtest_from_any_directory(monkeypatch, tmp_path, capsys, sample_analysis):
    monkeypatch.chdir(tmp_path)
    assert main(["--confidence", "0.95", "--window", "250"]) == 0
    output = capsys.readouterr().out
    assert f"market-risk-var-es {__version__}" in output
    assert "Kupiec unconditional coverage" in output
    assert "Christoffersen independence" in output
    assert "Christoffersen conditional coverage" in output
    assert "Not investment advice" in output
    assert "Historical" in output
    assert "Parametric" in output

    report = format_report(sample_analysis)
    assert "Confidence 99.00%" in report
    assert "not an Euler allocation" in report


def test_cli_reports_a_weight_error_on_stderr(capsys):
    assert main(["--weights", "SPY=0.5,AGG=0.4"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error:")


def test_cli_help_exits_cleanly():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_readme_example_matches_the_default_report(sample_analysis):
    readme = Path(__file__).resolve().parents[1] / "README.md"
    text = readme.read_text(encoding="utf-8")
    marker = "```text\nmarket-risk-var-es"
    start = text.index(marker) + len("```text\n")
    end = text.index("\n```", start)
    assert text[start:end] == format_report(sample_analysis).rstrip("\n")


def test_workflow_runs_only_this_project():
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "market-risk-var-es.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "working-directory: market-risk-var-es" in text
    assert "market-risk-var-es/**" in text
    assert "Algo-trading" not in text
    assert "mini-RPA" not in text
    assert "python -m pytest" in text
    assert "python -m ruff check ." in text
    assert "continue-on-error" not in text
