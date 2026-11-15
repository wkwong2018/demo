"""Plain-text report for the VaR / Expected Shortfall run."""

from __future__ import annotations

import math

import pandas as pd

from market_risk.analysis import AnalysisResult, ConfidenceResult
from market_risk.backtest import HypothesisTest, VarBacktest


def format_report(result: AnalysisResult) -> str:
    """Return the full text report, ending in a newline."""
    sections = [
        _header(result),
        _descriptive(result),
        *(_confidence_section(result, block) for block in result.blocks),
        (
            "Personal methodology demo on public market data. "
            "Not a risk limit. Not investment advice."
        ),
    ]
    return "\n\n".join(sections) + "\n"


def _header(result: AnalysisResult) -> str:
    if result.zero_mean:
        location = (
            "Parametric model: Gaussian variance-covariance with location fixed at 0. "
            "Volatility is still the sample standard deviation around the sample mean."
        )
    else:
        location = (
            "Parametric model: Gaussian variance-covariance using the sample mean "
            "and the sample covariance (divisor n - 1)."
        )
    weight_text = ", ".join(
        f"{ticker} {_percent(weight)}" for ticker, weight in result.weights.items()
    )
    lines = [
        f"market-risk-var-es {result.version}",
        "One-day (close-to-close) Value at Risk and Expected Shortfall",
        "",
        f"Portfolio value: {_amount(result.portfolio_value)}",
        f"Weights: {weight_text}",
        (
            f"Prices: {_date(result.price_start)} to {_date(result.price_end)} "
            f"({result.price_rows:,} sessions)"
        ),
        f"Simple returns: {result.return_rows:,}",
        (
            f"Current estimate: last {result.window} returns, "
            f"{_date(result.window_start)} to {_date(result.window_end)}, "
            "applied to the next session"
        ),
        location,
        (
            f"Backtest: rolling window of {result.window} returns. "
            "Each forecast uses only earlier sessions."
        ),
        "Exception: realized simple return < -VaR. A tie is not an exception.",
        f"Hypothesis tests are evaluated at the {_percent(result.significance, 0)} significance level.",
        "Losses are positive numbers. A negative VaR means the threshold outcome is a gain.",
    ]
    return "\n".join(lines)


def _descriptive(result: AnalysisResult) -> str:
    lines = [
        "Estimation window, descriptive",
        (
            f"Portfolio mean: {_percent(result.sample_mean, 4)} per session"
        ),
        (
            f"Portfolio volatility: {_percent(result.sample_volatility, 4)} per session "
            f"(sample, divisor n - 1)"
        ),
        (
            "Annualized volatility, sqrt(252) of that session volatility, "
            f"descriptive only: {_percent(result.annualized_volatility)}"
        ),
        "",
        "Asset volatility per session",
        _two_column(
            "Asset",
            "Volatility",
            [
                (ticker, _percent(float(vol), 4))
                for ticker, vol in result.asset_volatility.items()
            ],
        ),
        "",
        "Correlation, estimation window",
        _correlation(result.correlation),
    ]
    return "\n".join(lines)


def _confidence_section(result: AnalysisResult, block: ConfidenceResult) -> str:
    level = _percent(block.confidence, 2)
    rows = [
        _risk_row("Historical", block.historical.var_return, block.historical.es_return, result.portfolio_value),
        _risk_row("Parametric", block.parametric.var_return, block.parametric.es_return, result.portfolio_value),
    ]
    lines = [
        f"Confidence {level}",
        _columns(
            ["Method", "VaR return", "VaR amount", "ES return", "ES amount"],
            rows,
        ),
        _tail_note(result.window, block.confidence),
        "",
        (
            "Single-position VaR, each weight held on its own over the same window. "
            "This is not an Euler allocation. The rows do not sum to portfolio VaR."
        ),
        _standalone_table(result, block),
        "",
        _backtest_section("Historical VaR backtest", block.historical_backtest),
        "",
        _backtest_section("Parametric VaR backtest", block.parametric_backtest),
    ]
    return "\n".join(lines)


def _risk_row(
    label: str,
    var_return: float,
    es_return: float,
    portfolio_value: float,
) -> list[str]:
    return [
        label,
        _percent(var_return),
        _amount(var_return * portfolio_value),
        _percent(es_return),
        _amount(es_return * portfolio_value),
    ]


def _standalone_table(result: AnalysisResult, block: ConfidenceResult) -> str:
    rows = []
    for ticker in result.weights.index:
        rows.append(
            [
                ticker,
                _amount(float(block.historical_standalone.by_asset[ticker]) * result.portfolio_value),
                _amount(float(block.parametric_standalone.by_asset[ticker]) * result.portfolio_value),
            ]
        )
    rows.append(
        [
            "Sum",
            _amount(block.historical_standalone.total * result.portfolio_value),
            _amount(block.parametric_standalone.total * result.portfolio_value),
        ]
    )
    rows.append(
        [
            "Portfolio",
            _amount(block.historical.var_return * result.portfolio_value),
            _amount(block.parametric.var_return * result.portfolio_value),
        ]
    )
    rows.append(
        [
            "Sum minus portfolio",
            _amount(
                (block.historical_standalone.total - block.historical.var_return)
                * result.portfolio_value
            ),
            _amount(
                (block.parametric_standalone.total - block.parametric.var_return)
                * result.portfolio_value
            ),
        ]
    )
    return _columns(["Position", "Historical VaR", "Parametric VaR"], rows)


def _backtest_section(title: str, backtest: VarBacktest) -> str:
    start = _date(pd.Timestamp(backtest.dates[0]))
    end = _date(pd.Timestamp(backtest.dates[-1]))
    lines = [
        title,
        (
            f"Out of sample: {start} to {end} "
            f"({backtest.observations:,} sessions)"
        ),
        (
            f"Exceptions: {backtest.exceptions:,} "
            f"({_percent(backtest.exception_rate, 2)}), "
            f"expected {backtest.expected_exceptions:,.2f} "
            f"({_percent(backtest.alpha, 2)}). "
            f"The rate is {_rate_comment(backtest.exception_rate, backtest.alpha)}."
        ),
        (
            "Transitions: "
            f"n00={backtest.transitions.n00:,} "
            f"n01={backtest.transitions.n01:,} "
            f"n10={backtest.transitions.n10:,} "
            f"n11={backtest.transitions.n11:,}"
        ),
        (
            f"P(hit)={_rate(backtest.transitions.pi)}  "
            f"P(hit | no hit)={_optional_rate(backtest.transitions.pi01)}  "
            f"P(hit | hit)={_optional_rate(backtest.transitions.pi11)}"
        ),
        _test_line(backtest.kupiec),
        _test_line(backtest.independence),
        _test_line(backtest.conditional),
    ]
    return "\n".join(lines)


def _test_line(test: HypothesisTest) -> str:
    decision = "rejected" if test.rejected else "not rejected"
    return (
        f"{test.name}: LR={_statistic(test.statistic)}  "
        f"df={test.degrees_of_freedom}  "
        f"p-value={_p_value(test.p_value)}  "
        f"decision={decision}\n"
        f"  H0: {test.null_hypothesis}"
    )


def _tail_note(window: int, confidence: float) -> str:
    expected = window * (1.0 - confidence)
    if expected >= 5:
        return (
            f"The window has about {expected:.1f} expected tail observations "
            "at this confidence."
        )
    return (
        f"Note: the window has about {expected:.1f} expected tail observations "
        "at this confidence, so the historical quantile is coarse."
    )


def _rate_comment(rate: float, alpha: float) -> str:
    if abs(rate - alpha) <= 1e-15:
        return "in line with the model tail probability"
    if rate > alpha:
        return "above the model tail probability"
    return "below the model tail probability"


def _correlation(frame: pd.DataFrame) -> str:
    names = [str(name) for name in frame.columns]
    header = " " * 8 + "".join(f"{name:>8}" for name in names)
    lines = [header]
    for name in names:
        cells = [f"{name:<8}"]
        for other in names:
            value = float(frame.loc[name, other])
            cells.append(f"{value:8.2f}" if math.isfinite(value) else f"{'n/a':>8}")
        lines.append("".join(cells).rstrip())
    return "\n".join(line.rstrip() for line in lines)


def _columns(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    lines = ["  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)).rstrip()]
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)).rstrip())
    return "\n".join(lines)


def _two_column(left_header: str, right_header: str, rows: list[tuple[str, str]]) -> str:
    return _columns([left_header, right_header], [[left, right] for left, right in rows])


def _date(value: pd.Timestamp) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _amount(value: float) -> str:
    return f"{value:,.2f}"


def _percent(value: float, digits: int = 2) -> str:
    return f"{100.0 * value:.{digits}f}%"


def _rate(value: float) -> str:
    return f"{value:.4f}"


def _optional_rate(value: float | None) -> str:
    if value is None:
        return "n/a"
    return _rate(value)


def _statistic(value: float) -> str:
    if math.isinf(value):
        return "inf"
    return f"{value:.3f}"


def _p_value(value: float) -> str:
    if value < 1e-4:
        return f"{value:.2e}"
    return f"{value:.4f}"
