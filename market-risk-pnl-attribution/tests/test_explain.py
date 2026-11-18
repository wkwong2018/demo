"""Dollar identities and the edge cases the README describes."""

from __future__ import annotations

from decimal import Decimal

import pytest

from pnl_attribution import FactorReturn, Loading, Position, explain_book, make_book
from pnl_attribution.explain import InstrumentExplain
from pnl_attribution.report import format_report


def _row(
    position: Position,
    *,
    factors: list[FactorReturn] | None = None,
    loadings: list[Loading] | None = None,
) -> InstrumentExplain:
    if factors is None:
        factors = [FactorReturn("EQ", Decimal("0.1"))]
    if loadings is None:
        loadings = [Loading(str(position.instrument).strip(), "EQ", Decimal(1))]
    result = explain_book(make_book([position], factors, loadings, session="case"))
    return result.instruments[0]


def _assert_identities(row: InstrumentExplain) -> None:
    assert row.market_pnl + row.position_pnl + row.residual_pnl == row.session_pnl
    factor_sum = sum((amount for _, amount in row.factor_pnl), Decimal(0))
    assert factor_sum + row.specific_pnl == row.market_pnl
    assert row.market_value_change - row.cash_at_start == row.market_pnl + row.position_pnl


def test_hand_computed_split_and_two_factors():
    row = _row(
        Position("SYN", Decimal(10), Decimal(14), Decimal(5), Decimal(8)),
        factors=[FactorReturn("EQ", Decimal("0.5")), FactorReturn("RT", Decimal("0.2"))],
        loadings=[Loading("SYN", "EQ", Decimal(1)), Loading("SYN", "RT", Decimal(-1))],
    )
    _assert_identities(row)
    assert row.market_pnl == Decimal(30)
    assert row.position_pnl == Decimal(12)
    assert row.residual_pnl == Decimal(0)
    assert row.session_pnl == Decimal(42)
    assert row.cash_at_start == Decimal(20)
    assert row.market_value_change == Decimal(62)
    assert dict(row.factor_pnl) == {"EQ": Decimal(25), "RT": Decimal(-10)}
    assert row.specific_pnl == Decimal(15)
    assert row.actual_return == Decimal("0.6")
    assert row.predicted_return == Decimal("0.3")
    assert row.residual_return == Decimal("0.3")
    assert row.specific_pnl == row.qty_start * row.price_start * row.residual_return
    assert [name for name, _ in row.factor_pnl] == ["EQ", "RT"]


def test_reported_pnl_is_the_residual_and_can_be_zero():
    row = _row(Position("SYN", Decimal(10), Decimal(14), Decimal(5), Decimal(8), Decimal(40)))
    assert row.market_pnl == Decimal(30)
    assert row.position_pnl == Decimal(12)
    assert row.session_pnl == Decimal(40)
    assert row.residual_pnl == Decimal(-2)
    assert row.reported_supplied is True
    _assert_identities(row)

    exact = _row(Position("SYN", Decimal(10), Decimal(14), Decimal(5), Decimal(8), Decimal(42)))
    assert exact.residual_pnl == Decimal(0)
    assert exact.reported_supplied is True
    assert exact.session_pnl == Decimal(42)


def test_new_position_has_no_market_and_no_factor_pnl():
    row = _row(
        Position("NEW", Decimal(0), Decimal(3), Decimal(10), Decimal(13)),
        factors=[FactorReturn("EQ", Decimal("0.5"))],
        loadings=[Loading("NEW", "EQ", Decimal(1))],
    )
    _assert_identities(row)
    assert row.market_pnl == Decimal(0)
    assert row.position_pnl == Decimal(9)
    assert row.session_pnl == Decimal(9)
    assert dict(row.factor_pnl) == {"EQ": Decimal(0)}
    assert row.specific_pnl == Decimal(0)
    assert row.actual_return == Decimal("0.3")
    assert row.residual_return == Decimal("-0.2")
    assert row.qty_start * row.price_start * row.residual_return == Decimal(0)


def test_closed_position_offsets_the_market_move():
    row = _row(
        Position("OLD", Decimal(5), Decimal(0), Decimal(10), Decimal(7)),
        factors=[FactorReturn("EQ", Decimal("0.1"))],
        loadings=[Loading("OLD", "EQ", Decimal(1))],
    )
    _assert_identities(row)
    assert row.market_pnl == Decimal(-15)
    assert row.position_pnl == Decimal(15)
    assert row.session_pnl == Decimal(0)
    assert dict(row.factor_pnl) == {"EQ": Decimal(5)}
    assert row.specific_pnl == Decimal(-20)
    assert row.session_pnl != row.market_pnl


def test_zero_price_move_has_zero_market_and_position_pnl():
    row = _row(
        Position("FLAT", Decimal(2), Decimal(9), Decimal(4), Decimal(4)),
        factors=[FactorReturn("EQ", Decimal("0.25"))],
        loadings=[Loading("FLAT", "EQ", Decimal(1))],
    )
    _assert_identities(row)
    assert row.market_pnl == Decimal(0)
    assert row.position_pnl == Decimal(0)
    assert row.session_pnl == Decimal(0)
    assert row.cash_at_start == Decimal(28)
    assert row.market_value_change == Decimal(28)
    assert dict(row.factor_pnl) == {"EQ": Decimal(2)}
    assert row.specific_pnl == Decimal(-2)


def test_shorts_gain_when_the_price_falls_and_lose_when_it_rises():
    down = _row(Position("SHORT", Decimal(-4), Decimal(-4), Decimal(10), Decimal(8)))
    up = _row(Position("SHORT", Decimal(-4), Decimal(-4), Decimal(10), Decimal(12)))
    _assert_identities(down)
    _assert_identities(up)
    assert down.position_pnl == Decimal(0)
    assert up.position_pnl == Decimal(0)
    assert down.market_pnl == Decimal(8)
    assert down.session_pnl == Decimal(8)
    assert up.market_pnl == Decimal(-8)
    assert up.session_pnl == Decimal(-8)


def test_constant_quantity_has_zero_position_pnl():
    row = _row(Position("HELD", Decimal(4), Decimal(4), Decimal(10), Decimal(11)))
    assert row.position_pnl == Decimal(0)
    assert row.session_pnl == row.market_pnl == Decimal(4)


def test_no_loading_makes_specific_equal_market():
    row = _row(
        Position("A", Decimal(2), Decimal(2), Decimal(5), Decimal(7)),
        factors=[FactorReturn("EQ", Decimal("0.1"))],
        loadings=[],
    )
    assert dict(row.factor_pnl) == {"EQ": Decimal(0)}
    assert row.predicted_return == Decimal(0)
    assert row.specific_pnl == row.market_pnl == Decimal(4)
    _assert_identities(row)


def test_zero_beta_contributes_nothing():
    row = _row(
        Position("A", Decimal(1), Decimal(1), Decimal(10), Decimal(11)),
        factors=[FactorReturn("EQ", Decimal("0.5"))],
        loadings=[Loading("A", "EQ", Decimal(0))],
    )
    assert dict(row.factor_pnl) == {"EQ": Decimal(0)}
    assert row.specific_pnl == row.market_pnl == Decimal(1)


def test_factor_return_is_not_clipped():
    row = _row(
        Position("A", Decimal(1), Decimal(1), Decimal(10), Decimal(11)),
        factors=[FactorReturn("EQ", Decimal(-2))],
        loadings=[Loading("A", "EQ", Decimal(1))],
    )
    assert row.market_pnl == Decimal(1)
    assert dict(row.factor_pnl) == {"EQ": Decimal(-20)}
    assert row.specific_pnl == Decimal(21)
    _assert_identities(row)


def test_factor_order_follows_the_factor_list():
    row = _row(
        Position("A", Decimal(1), Decimal(1), Decimal(10), Decimal(10)),
        factors=[FactorReturn("RT", Decimal("0.1")), FactorReturn("EQ", Decimal("0.2"))],
        loadings=[Loading("A", "EQ", Decimal(1))],
    )
    assert [name for name, _ in row.factor_pnl] == ["RT", "EQ"]


def test_inexact_simple_return_does_not_replace_the_dollar_plug():
    row = _row(
        Position("SYN", Decimal(1), Decimal(1), Decimal(3), Decimal(4)),
        factors=[FactorReturn("EQ", Decimal("0.1"))],
        loadings=[Loading("SYN", "EQ", Decimal(1))],
    )
    _assert_identities(row)
    assert row.market_pnl == Decimal(1)
    assert dict(row.factor_pnl) == {"EQ": Decimal("0.3")}
    assert row.specific_pnl == Decimal("0.7")
    opening = row.qty_start * row.price_start
    assert row.specific_pnl != opening * row.residual_return


@pytest.mark.parametrize(
    ("q0", "q1", "p0", "p1", "reported"),
    [
        ("10", "14", "5", "8", None),
        ("-4", "-4", "10", "12", None),
        ("0", "3", "10", "13", None),
        ("5", "0", "10", "7", None),
        ("2", "9", "4", "4", None),
        ("1", "1", "3", "4", None),
        ("-2.5", "1.5", "8", "7.5", "1.25"),
        ("100", "100", "1", "1", "0"),
    ],
)
def test_dollar_identities_on_a_fixed_grid(q0, q1, p0, p1, reported):
    reported_value = None if reported is None else Decimal(reported)
    start_qty = Decimal(q0)
    end_qty = Decimal(q1)
    start_px = Decimal(p0)
    end_px = Decimal(p1)
    row = _row(
        Position("SYN", start_qty, end_qty, start_px, end_px, reported_value),
        factors=[FactorReturn("EQ", Decimal("0.1")), FactorReturn("RT", Decimal("-0.25"))],
        loadings=[Loading("SYN", "EQ", Decimal("0.5")), Loading("SYN", "RT", Decimal(-1))],
    )
    _assert_identities(row)
    delta = end_px - start_px
    assert row.market_pnl == start_qty * delta
    assert row.position_pnl == (end_qty - start_qty) * delta
    if reported_value is None:
        assert row.residual_pnl == Decimal(0)
        assert row.session_pnl == end_qty * delta
    else:
        assert row.session_pnl == reported_value
        assert row.residual_pnl == reported_value - (row.market_pnl + row.position_pnl)


def test_sample_book_matches_the_documented_numbers(sample_result):
    assert sample_result.market_pnl == Decimal(2500)
    assert sample_result.position_pnl == Decimal(960)
    assert sample_result.residual_pnl == Decimal(0)
    assert sample_result.session_pnl == Decimal(3460)
    assert sample_result.cash_at_start == Decimal(9000)
    assert sample_result.market_value_change == Decimal(12460)
    assert sample_result.market_value_change - sample_result.cash_at_start == Decimal(3460)
    assert dict(sample_result.factor_totals()) == {
        "EQ": Decimal(1200),
        "RT": Decimal(650),
        "FX": Decimal(210),
    }
    assert sample_result.specific_pnl == Decimal(440)
    factor_sum = sum((amount for _, amount in sample_result.factor_totals()), Decimal(0))
    assert factor_sum + sample_result.specific_pnl == sample_result.market_pnl
    assert sample_result.uses_reported_pnl is False

    expected = {
        "SYN-EQ-A": ("1000", "0", "1000", "1000", "0", "0", "0"),
        "SYN-EQ-B": ("400", "160", "560", "200", "50", "0", "150"),
        "SYN-RT-A": ("1000", "0", "1000", "0", "500", "0", "500"),
        "SYN-FX-A": ("500", "0", "500", "0", "0", "250", "250"),
        "SYN-EQ-C": ("0", "400", "400", "0", "0", "0", "0"),
        "SYN-RT-B": ("-400", "400", "0", "0", "100", "0", "-500"),
        "SYN-FX-B": ("0", "0", "0", "0", "0", "-40", "40"),
    }
    assert [row.instrument for row in sample_result.instruments] == list(expected)
    for row in sample_result.instruments:
        market, position, session, eq, rt, fx, specific = expected[row.instrument]
        assert row.market_pnl == Decimal(market)
        assert row.position_pnl == Decimal(position)
        assert row.residual_pnl == Decimal(0)
        assert row.session_pnl == Decimal(session)
        assert dict(row.factor_pnl) == {"EQ": Decimal(eq), "RT": Decimal(rt), "FX": Decimal(fx)}
        assert row.specific_pnl == Decimal(specific)
        _assert_identities(row)
        opening = row.qty_start * row.price_start
        assert row.specific_pnl == opening * row.residual_return
        assert row.market_pnl == row.market_pnl.quantize(Decimal("0.01"))
        assert (row.actual_return * 100) == (row.actual_return * 100).quantize(Decimal("0.01"))
        assert (row.residual_return * 100) == (row.residual_return * 100).quantize(Decimal("0.01"))

    resized = next(row for row in sample_result.instruments if row.instrument == "SYN-EQ-B")
    assert sum((amount for _, amount in resized.factor_pnl), Decimal(0)) + resized.specific_pnl != resized.session_pnl
    opened = next(row for row in sample_result.instruments if row.instrument == "SYN-EQ-C")
    assert opened.residual_return == Decimal("0.01")
    assert opened.specific_pnl == Decimal(0)


def test_sample_report_has_no_signed_zero(sample_result):
    text = format_report(sample_result)
    assert "-0.00" not in text
    assert text.endswith("Not affiliated with any employer.\n")
