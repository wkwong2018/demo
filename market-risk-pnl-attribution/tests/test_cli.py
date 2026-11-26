"""CLI, README, and the path-filtered workflow."""

from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from pnl_attribution import __version__, explain_book, load_sample_book
from pnl_attribution.cli import main
from pnl_attribution.report import format_report


def test_cli_prints_the_sample_from_any_directory(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert f"market-risk-pnl-attribution {__version__}" in captured.out
    assert "Session label: 2026-06-12" in captured.out
    assert "Session P&L  3,460.00" in captured.out
    assert "Not affiliated with any employer" in captured.out
    assert "Not investment advice" in captured.out
    assert "synthetic" in captured.out.lower()
    assert "-0.00" not in captured.out


def test_session_label_does_not_change_the_pnl(capsys):
    assert main(["--session", "label-only"]) == 0
    output = capsys.readouterr().out
    assert "Session label: label-only" in output
    assert "3,460.00" in output
    assert explain_book(load_sample_book(session="label-only")).session_pnl == Decimal(3460)


def test_cli_reports_a_data_error_on_stderr(tmp_path, capsys):
    assert main(["--positions", str(tmp_path / "missing.csv")]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error:")


def test_cli_help_exits_cleanly():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_cli_reads_explicit_files(tmp_path, capsys):
    positions = tmp_path / "positions.csv"
    factors = tmp_path / "factors.csv"
    loadings = tmp_path / "loadings.csv"
    positions.write_text(
        "instrument,qty_start,qty_end,price_start,price_end\nSYN-Z,2,2,10,12\n",
        encoding="utf-8",
    )
    factors.write_text("factor,simple_return\nF,0.1\n", encoding="utf-8")
    loadings.write_text("instrument,factor,beta\nSYN-Z,F,1\n", encoding="utf-8")
    assert main(
        [
            "--positions",
            str(positions),
            "--factors",
            str(factors),
            "--loadings",
            str(loadings),
            "--session",
            "custom",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "Session label: custom" in output
    assert "SYN-Z" in output
    assert "Session P&L" in output
    assert "4.00" in output


def test_python_module_entrypoint(tmp_path):
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[1] / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not existing else src + os.pathsep + existing
    completed = subprocess.run(
        [sys.executable, "-m", "pnl_attribution"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    assert "market-risk-pnl-attribution 0.1.0" in completed.stdout
    assert completed.stderr == ""


def test_readme_example_matches_the_default_report(sample_result):
    readme = Path(__file__).resolve().parents[1] / "README.md"
    text = readme.read_text(encoding="utf-8")
    marker = "```text\nmarket-risk-pnl-attribution"
    start = text.index(marker) + len("```text\n")
    end = text.index("\n```", start)
    assert text[start:end] == format_report(sample_result).rstrip("\n")
    assert "market-risk-var-es" in text
    assert "market-risk-streaming-lake" in text
    assert "Not affiliated with any employer" in text
    assert "Not investment advice" in text
    assert "synthetic" in text.lower()


def test_root_readme_links_this_project():
    text = Path(__file__).resolve().parents[2].joinpath("README.md").read_text(encoding="utf-8")
    assert "[market-risk-pnl-attribution](market-risk-pnl-attribution/)" in text


def test_workflow_runs_only_this_project():
    workflow = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "market-risk-pnl-attribution.yml"
    )
    text = workflow.read_text(encoding="utf-8")
    assert "working-directory: market-risk-pnl-attribution" in text
    assert "market-risk-pnl-attribution/**" in text
    assert '.github/workflows/market-risk-pnl-attribution.yml' in text
    assert 'python-version: "3.12"' in text
    assert 'pip install -e ".[dev]"' in text
    assert "python -m pytest" in text
    assert "ruff check --select E4,E7,E9,F src tests" in text
    assert "continue-on-error" not in text
    assert "pull_request_target" not in text
    assert "Algo-trading" not in text
    assert "market-risk-var-es" not in text
    assert "market-risk-streaming-lake" not in text


def test_agents_note_prefers_tests_over_a_weaker_check():
    text = Path(__file__).resolve().parents[1].joinpath("AGENTS.md").read_text(encoding="utf-8")
    assert "synthetic" in text.lower() or "public" in text.lower()
    assert "Do not relax" in text


def test_package_does_not_import_the_sibling_projects():
    root = Path(__file__).resolve().parents[1] / "src"
    for path in root.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert "market_risk" not in stripped
                assert "risk_lake" not in stripped


def test_project_text_does_not_copy_sibling_desk_names():
    root = Path(__file__).resolve().parents[1]
    paths = [
        root / "README.md",
        root / "AGENTS.md",
        root / "pyproject.toml",
        * (root / "src").rglob("*.py"),
        * (root / "data").rglob("*.csv"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
    for banned in ("eq-delta", "fi-rates", "book-a", "kafka", "azure", "openai"):
        assert banned not in text
