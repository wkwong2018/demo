"""Loader and validation tests for the snapshot files."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from pnl_attribution import (
    SAMPLE_SESSION,
    Book,
    FactorReturn,
    Loading,
    PnlAttributionError,
    Position,
    load_book,
    load_sample_book,
    make_book,
)
from pnl_attribution.explain import explain_book

_FACTORS = "factor,simple_return\nEQ,0.01\n"
_LOADINGS = "instrument,factor,beta\nA,EQ,1\n"


def _write(directory: Path, positions: str, factors: str = _FACTORS, loadings: str = _LOADINGS):
    positions_path = directory / "positions.csv"
    factors_path = directory / "factors.csv"
    loadings_path = directory / "loadings.csv"
    positions_path.write_text(positions, encoding="utf-8")
    factors_path.write_text(factors, encoding="utf-8")
    loadings_path.write_text(loadings, encoding="utf-8")
    return positions_path, factors_path, loadings_path


def test_sample_book_is_the_shipped_snapshot():
    book = load_sample_book()
    assert book.session == SAMPLE_SESSION
    assert book.currency == "USD"
    assert [row.instrument for row in book.positions] == [
        "SYN-EQ-A",
        "SYN-EQ-B",
        "SYN-RT-A",
        "SYN-FX-A",
        "SYN-EQ-C",
        "SYN-RT-B",
        "SYN-FX-B",
    ]
    assert [(row.factor, row.simple_return) for row in book.factors] == [
        ("EQ", Decimal("0.01")),
        ("RT", Decimal("0.005")),
        ("FX", Decimal("-0.02")),
    ]
    assert all(row.reported_pnl is None for row in book.positions)
    short = next(row for row in book.positions if row.instrument == "SYN-FX-A")
    assert short.qty_start == Decimal("-10000")
    opened = next(row for row in book.positions if row.instrument == "SYN-EQ-C")
    assert opened.qty_start == Decimal(0)


def test_sample_loads_from_another_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert len(load_sample_book().positions) == 7


def test_headers_ignore_case_and_surrounding_space(tmp_path):
    paths = _write(
        tmp_path,
        " Instrument , Qty_Start , Qty_End , Price_Start , Price_End \n"
        " SYN-A , 2 , 2 , 10 , 12 \n",
        " Factor , Simple_Return \n F , 0.1 \n",
        " Instrument , Factor , Beta \n SYN-A , F , 1 \n",
    )
    book = load_book(*paths)
    row = explain_book(book).instruments[0]
    assert row.market_pnl == Decimal(4)
    assert row.position_pnl == Decimal(0)
    assert dict(row.factor_pnl)["F"] == Decimal(2)
    assert row.specific_pnl == Decimal(2)


def test_blank_reported_pnl_is_absent_and_zero_is_present(tmp_path):
    paths = _write(
        tmp_path,
        "instrument,qty_start,qty_end,price_start,price_end,reported_pnl\n"
        "A,1,1,10,12,0\n"
        "B,1,1,10,12,\n",
        loadings="instrument,factor,beta\nA,EQ,1\nB,EQ,1\n",
    )
    result = explain_book(load_book(*paths))
    reported, omitted = result.instruments
    assert reported.reported_supplied is True
    assert reported.session_pnl == Decimal(0)
    assert reported.residual_pnl == Decimal(-2)
    assert omitted.reported_supplied is False
    assert omitted.residual_pnl == Decimal(0)
    assert omitted.session_pnl == Decimal(2)
    assert result.uses_reported_pnl is True


def test_empty_loadings_file_is_allowed(tmp_path):
    paths = _write(tmp_path, "instrument,qty_start,qty_end,price_start,price_end\nA,1,1,10,11\n", loadings="instrument,factor,beta\n")
    result = explain_book(load_book(*paths))
    row = result.instruments[0]
    assert row.specific_pnl == row.market_pnl == Decimal(1)
    assert dict(row.factor_pnl) == {"EQ": Decimal(0)}


def test_integers_are_accepted_and_floats_are_rejected():
    book = make_book(
        [Position("A", 1, 2, 10, 11)],
        [FactorReturn("F", 0)],
        [Loading("A", "F", 1)],
    )
    assert book.positions[0].qty_start == Decimal(1)
    row = explain_book(book).instruments[0]
    assert row.market_pnl == Decimal(1)
    assert row.position_pnl == Decimal(1)
    assert row.session_pnl == Decimal(2)

    with pytest.raises(PnlAttributionError, match="Decimal or an int"):
        make_book(
            [Position("A", 1.0, 1, 10, 11)],
            [FactorReturn("F", 0)],
            [],
        )
    with pytest.raises(PnlAttributionError, match="Decimal or an int"):
        make_book(
            [Position("A", True, 1, 10, 11)],
            [FactorReturn("F", 0)],
            [],
        )


def test_explain_validates_a_hand_built_book():
    book = Book(
        positions=(Position("A", Decimal(1), Decimal(1), Decimal(-1), Decimal(1)),),
        factors=(FactorReturn("F", Decimal(0)),),
        loadings=(),
    )
    with pytest.raises(PnlAttributionError, match="positive"):
        explain_book(book)


@pytest.mark.parametrize(
    ("positions", "factors", "loadings", "match"),
    [
        (
            "instrument,qty_start,qty_end,price_start,price_end\n",
            _FACTORS,
            _LOADINGS,
            "at least one instrument",
        ),
        (
            "instrument,qty_start,qty_end,price_start,price_end\nA,1,1,10,11\n",
            "factor,simple_return\n",
            "instrument,factor,beta\n",
            "at least one factor",
        ),
        (
            "instrument,qty_start,qty_end,price_start,price_end\nA,1,1,0,11\n",
            _FACTORS,
            _LOADINGS,
            "positive",
        ),
        (
            "instrument,qty_start,qty_end,price_start,price_end\nA,1,1,10,-1\n",
            _FACTORS,
            _LOADINGS,
            "positive",
        ),
        (
            "instrument,qty_start,qty_end,price_start,price_end\nA,1,1,10,11\nA,1,1,10,11\n",
            _FACTORS,
            _LOADINGS,
            "duplicate instrument",
        ),
        (
            "instrument,qty_start,qty_end,price_start,price_end\nA,ten,1,10,11\n",
            _FACTORS,
            _LOADINGS,
            "not a number",
        ),
        (
            "instrument,qty_start,qty_end,price_start,price_end\nA,1,1,10,11\n",
            "factor,simple_return\nEQ,NaN\n",
            _LOADINGS,
            "not finite",
        ),
        (
            "instrument,qty_start,qty_end,price_start\nA,1,1,10\n",
            _FACTORS,
            _LOADINGS,
            "missing column",
        ),
        (
            "instrument,qty_start,qty_end,price_start,price_end,note\nA,1,1,10,11,x\n",
            _FACTORS,
            _LOADINGS,
            "unexpected column",
        ),
        (
            "instrument,qty_start,qty_end,price_start,price_end\nA,1,1,10,11,extra\n",
            _FACTORS,
            _LOADINGS,
            "too many columns",
        ),
        (
            "instrument,qty_start,qty_end,price_start,price_end\nA,1,1,10,11\n",
            "factor,simple_return\nEQ,0.01\nEQ,0.02\n",
            _LOADINGS,
            "duplicate factor",
        ),
        (
            "instrument,qty_start,qty_end,price_start,price_end\nA,1,1,10,11\n",
            _FACTORS,
            "instrument,factor,beta\nA,EQ,1\nA,EQ,2\n",
            "duplicate loading",
        ),
        (
            "instrument,qty_start,qty_end,price_start,price_end\nA,1,1,10,11\n",
            _FACTORS,
            "instrument,factor,beta\nMISSING,EQ,1\n",
            "unknown instrument",
        ),
        (
            "instrument,qty_start,qty_end,price_start,price_end\nA,1,1,10,11\n",
            _FACTORS,
            "instrument,factor,beta\nA,NOPE,1\n",
            "unknown factor",
        ),
    ],
)
def test_loader_rejects_bad_inputs(tmp_path, positions, factors, loadings, match):
    paths = _write(tmp_path, positions, factors, loadings)
    with pytest.raises(PnlAttributionError, match=match):
        load_book(*paths)


def test_missing_file_and_bad_labels(tmp_path):
    with pytest.raises(PnlAttributionError, match="file not found"):
        load_book(tmp_path / "missing.csv", tmp_path / "factors.csv", tmp_path / "loadings.csv")
    with pytest.raises(PnlAttributionError, match="session label"):
        make_book(
            [Position("A", 1, 1, 10, 11)],
            [FactorReturn("F", 0)],
            [],
            session="two words",
        )
    with pytest.raises(PnlAttributionError, match="USD"):
        make_book(
            [Position("A", 1, 1, 10, 11)],
            [FactorReturn("F", 0)],
            [],
            currency="EUR",
        )
