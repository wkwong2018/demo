"""Plain-text session P&L report."""

from __future__ import annotations

from decimal import Decimal

from pnl_attribution.explain import ExplainResult


def format_report(result: ExplainResult) -> str:
    """Return the full text report, ending in a newline."""
    sections = [
        _header(result),
        _factor_returns(result),
        _loadings(result),
        _instruments(result),
        _session_identity(result),
        _cash(result),
        _factor_totals(result),
        _factor_detail(result),
        _returns(result),
        (
            "Personal interview demo on synthetic data. "
            "Not a production risk system. Not investment advice. "
            "Not affiliated with any employer."
        ),
    ]
    return "\n\n".join(sections) + "\n"


def _header(result: ExplainResult) -> str:
    count = len(result.instruments)
    noun = "instrument" if count == 1 else "instruments"
    if result.uses_reported_pnl:
        residual = (
            "At least one instrument has a reported session P&L. "
            "Residual = reported session P&L - market P&L - position P&L."
        )
    else:
        residual = (
            "No reported session P&L was supplied. "
            "Residual is 0, and session P&L is market P&L + position P&L."
        )
    lines = [
        f"market-risk-pnl-attribution {result.version}",
        "Session P&L explain for a linear snapshot book",
        "",
        f"Session label: {result.session}",
        f"Currency: {result.currency}",
        f"Book: {count} {noun}",
        "Data: synthetic snapshot. No market download.",
        "",
        "Session P&L = market P&L + position P&L + residual.",
        "Market P&L = start quantity x (end price - start price).",
        "Position P&L = quantity change x (end price - start price).",
        "Quantity changes are dealt at the start price. There is no trade tape.",
        residual,
        (
            "Factor P&L = opening market value x stated beta x stated factor simple return. "
            "The betas are inputs, not a fitted model."
        ),
        "Factor P&L + specific P&L = market P&L. Position P&L is outside that sum.",
        "A gain is positive. Prices are positive USD amounts. Short quantities are allowed.",
        "Factor names are labels. Nothing here treats a factor as a yield, a curve, or a currency conversion.",
    ]
    return "\n".join(lines)


def _factor_returns(result: ExplainResult) -> str:
    rows = [[factor.factor, _percent(factor.simple_return)] for factor in result.factors]
    return "\n".join(
        [
            "Factor simple returns",
            "These returns are inputs. They are not estimated from the instrument prices.",
            _table(["Factor", "Return"], rows, numeric=frozenset({1})),
        ]
    )


def _loadings(result: ExplainResult) -> str:
    if not result.loadings:
        body = "No loadings were supplied. Market P&L is entirely specific."
    else:
        body = _table(
            ["Instrument", "Factor", "Beta"],
            [[loading.instrument, loading.factor, _plain(loading.beta)] for loading in result.loadings],
            numeric=frozenset({2}),
        )
    return "\n".join(
        [
            "Stated betas",
            "A missing instrument here has no factor loading. Its market P&L is specific.",
            body,
        ]
    )


def _instruments(result: ExplainResult) -> str:
    rows = [
        [
            row.instrument,
            _amount(row.qty_start),
            _amount(row.qty_end),
            _amount(row.price_start),
            _amount(row.price_end),
            _amount(row.market_pnl),
            _amount(row.position_pnl),
            _amount(row.residual_pnl),
            _amount(row.session_pnl),
        ]
        for row in result.instruments
    ]
    return "\n".join(
        [
            "Instrument P&L",
            _table(
                [
                    "Instrument",
                    "Qty start",
                    "Qty end",
                    "Px start",
                    "Px end",
                    "Market",
                    "Position",
                    "Residual",
                    "Session",
                ],
                rows,
                numeric=frozenset({1, 2, 3, 4, 5, 6, 7, 8}),
            ),
        ]
    )


def _session_identity(result: ExplainResult) -> str:
    rows = [
        ["Market", _amount(result.market_pnl)],
        ["Position", _amount(result.position_pnl)],
        ["Residual", _amount(result.residual_pnl)],
        ["Session P&L", _amount(result.session_pnl)],
    ]
    return "\n".join(
        [
            "Session identity",
            "Market + position + residual = session P&L.",
            _table(["Component", "Amount"], rows, numeric=frozenset({1})),
        ]
    )


def _cash(result: ExplainResult) -> str:
    model = result.market_pnl + result.position_pnl
    rows = [
        ["Market-value change", _amount(result.market_value_change)],
        ["Cash at the start price", _amount(result.cash_at_start)],
        ["Change minus cash", _amount(result.market_value_change - result.cash_at_start)],
        ["Market + position", _amount(model)],
    ]
    return "\n".join(
        [
            "Market value and cash",
            "Cash is the quantity change times the start price.",
            "Buying units at the start price changes market value and does not, by itself, create P&L.",
            "Market-value change minus cash equals market P&L + position P&L.",
            "Session P&L equals that sum plus the residual.",
            _table(["Component", "Amount"], rows, numeric=frozenset({1})),
        ]
    )


def _factor_totals(result: ExplainResult) -> str:
    rows = [[name, _amount(amount)] for name, amount in result.factor_totals()]
    rows.append(["Specific", _amount(result.specific_pnl)])
    rows.append(["Market P&L", _amount(result.market_pnl)])
    return "\n".join(
        [
            "Factor attribution of market P&L",
            "Each contribution is opening market value x beta x factor simple return.",
            "The rows below sum to market P&L. They do not sum to session P&L.",
            _table(["Component", "Amount"], rows, numeric=frozenset({1})),
        ]
    )


def _factor_detail(result: ExplainResult) -> str:
    names = [name for name, _ in result.factor_totals()]
    headers = ["Instrument", "Market", *names, "Specific"]
    rows = []
    for row in result.instruments:
        amounts = [amount for _, amount in row.factor_pnl]
        rows.append(
            [
                row.instrument,
                _amount(row.market_pnl),
                *[_amount(amount) for amount in amounts],
                _amount(row.specific_pnl),
            ]
        )
    return "\n".join(
        [
            "Instrument factor split",
            "A zero means the opening market value, the beta, or the factor return produced zero.",
            "A new position has opening market value zero, so every factor dollar is zero.",
            _table(headers, rows, numeric=frozenset(range(1, len(headers)))),
        ]
    )


def _returns(result: ExplainResult) -> str:
    rows = [
        [
            row.instrument,
            _percent(row.actual_return),
            _percent(row.predicted_return),
            _percent(row.residual_return),
        ]
        for row in result.instruments
    ]
    return "\n".join(
        [
            "Price returns",
            "Actual is the instrument simple return. Predicted is the sum of beta x factor return.",
            "Specific P&L equals opening market value times the residual return when that division is exact.",
            "The dollar identity does not depend on the division. A new position can show a residual return and specific P&L of 0.",
            _table(
                ["Instrument", "Actual", "Predicted", "Residual return"],
                rows,
                numeric=frozenset({1, 2, 3}),
            ),
        ]
    )


def _table(headers: list[str], rows: list[list[str]], *, numeric: frozenset[int]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def render(cells: list[str]) -> str:
        parts = []
        for index, cell in enumerate(cells):
            if index in numeric:
                parts.append(cell.rjust(widths[index]))
            else:
                parts.append(cell.ljust(widths[index]))
        return "  ".join(parts).rstrip()

    return "\n".join([render(headers), *[render(row) for row in rows]])


def _amount(value: Decimal) -> str:
    scaled = value.quantize(Decimal("0.01"))
    if scaled.is_zero():
        scaled = Decimal(0)
    return f"{scaled:,.2f}"


def _percent(value: Decimal) -> str:
    scaled = (value * Decimal(100)).quantize(Decimal("0.01"))
    if scaled.is_zero():
        scaled = Decimal(0)
    return f"{scaled:.2f}%"


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." not in text:
        text += ".0"
    return text
